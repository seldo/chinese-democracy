"""trigger-boundary pipeline: the same 12 facts asked through 11 request forms -> judge (shared with direct-questions) -> form-by-model grids."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from collections import Counter
from functools import lru_cache

import numpy as np
import pandas as pd

from dq import pipeline as dqp
from dq.pipeline import CLASSES, JUDGE_SCHEMA, JUDGE_SYSTEM, NON_ANSWER, detect_lang, policy_cue, truncated_empty
from wcommon import stats
from wcommon.config import Model, append_jsonl, load_models, n_tokens, now_iso, read_jsonl, test_paths
from wcommon.fireworks import FireworksClient
from wcommon.gen import Job, load_raw, new_run_id, print_projection, print_stats, run_jobs, spend
from wcommon.judge import JudgeRequest, judge_model, judge_spend, load_judged, result_ok, run_batch, run_sync
from wcommon.lexicon import total_hits
from wcommon.report import models_table, spend_table

from . import materials
from .materials import GROUPS, LANGS

log = logging.getLogger("tb.pipeline")
P = test_paths(__file__)
MAX_TOKENS = 8192  # quiz and guide forms plus reasoning overran 4,096 on GLM-5.3 and Qwen in the dry run
TEMPERATURE = 0.6
N_SAMPLES = 3
THRESHOLD_USD = 50.0
JUDGED = P.judged / "answers.jsonl"
BATCH_STATE = P.judged / "batches.json"
FORM_IDS = [f["id"] for f in materials.load_forms()]
MULTI = "F10"


def item_id(fid: str, form_id: str, lang: str, stage: str = "") -> str:
    return f"{fid}:{form_id}{stage}:{lang}"


# ------------------------------------------------------------------ generation
def _messages(system: str | None, user_turns: list[str], prior: list[tuple[str, str]] = ()) -> list[dict]:
    msgs = [{"role": "system", "content": system}] if system else []
    for u, a in prior:
        msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
    msgs.append({"role": "user", "content": user_turns[-1]})
    return msgs


def make_jobs(models: list[Model], fids: list[str], form_ids: list[str], langs: list[str], samples: list[int], stage: int) -> list[Job]:
    """stage 1: every single-turn form plus turn 1 of the multi-turn form; stage 2: turn 2 of the multi-turn form, using the stored turn-1 answer."""
    jobs = []
    for m in models:
        raw1 = {(r["item_id"], r["sample_idx"]): r for r in load_raw(P.raw, m)} if stage == 2 else {}
        for fid in fids:
            f = materials.fact(fid)
            for form_id in form_ids:
                for lang in langs:
                    system, turns = materials.turns(form_id, f, lang)
                    meta = {"fid": fid, "group": f["group"], "topic": f["topic"], "form": form_id, "lang": lang}
                    for s in samples:
                        if form_id == MULTI:
                            if stage == 1:
                                jobs.append(Job(model=m, item_id=item_id(fid, form_id, lang, "a"), sample_idx=s, messages=_messages(system, turns[:1]), max_tokens=MAX_TOKENS, meta={**meta, "stage": "turn1"}))
                            else:
                                r1 = raw1.get((item_id(fid, form_id, lang, "a"), s))
                                if not r1 or not (r1.get("response") or "").strip():
                                    continue
                                jobs.append(Job(model=m, item_id=item_id(fid, form_id, lang), sample_idx=s, messages=_messages(system, turns, prior=[(turns[0], r1["response"])]), max_tokens=MAX_TOKENS, meta={**meta, "stage": "turn2"}))
                        elif stage == 1:
                            jobs.append(Job(model=m, item_id=item_id(fid, form_id, lang), sample_idx=s, messages=_messages(system, turns), max_tokens=MAX_TOKENS, meta=meta))
    return jobs


def cmd_generate(args, scope: str) -> None:
    models = load_models(args.models)
    all_f = [f["id"] for f in materials.load_facts()]
    china = [f["id"] for f in materials.load_facts() if f["group"] == "china"]
    control = [f["id"] for f in materials.load_facts() if f["group"] == "control"]
    if scope == "smoke":
        fids, forms, langs, samples = china[:1], ["F1", "F6", "F8", MULTI], ["en"], [0]
    elif scope == "dry":
        fids, forms, langs, samples = china[:2] + control[:1], FORM_IDS, list(LANGS), [0]
    else:
        fids, forms, langs, samples = all_f, FORM_IDS, list(LANGS), list(range(N_SAMPLES))
    full_calls = len(all_f) * (len(FORM_IDS) + 1) * len(LANGS) * N_SAMPLES  # +1 for the multi-turn form's first turn
    if scope == "full" and not args.yes:
        total = print_projection(P.raw, models, full_calls, THRESHOLD_USD)
        if total > THRESHOLD_USD:
            print(f"\nProjected remaining spend ${total:.2f} exceeds ${THRESHOLD_USD:.0f}. Re-run with --yes to proceed.")
            sys.exit(2)
    run_id = new_run_id(scope)
    for stage in (1, 2):
        client = FireworksClient(P.raw / "retries.log", global_concurrency=args.concurrency, per_model_concurrency=args.per_model)  # fresh client per stage: asyncio semaphores bind to one event loop
        jobs = make_jobs(models, fids, forms, langs, samples, stage)
        log.info("run_id=%s scope=%s stage=%d jobs=%d", run_id, scope, stage, len(jobs))
        st = asyncio.run(run_jobs(jobs, P.raw, run_id, client, temperature=TEMPERATURE))
        print_stats(st)
        append_jsonl(P.raw / "runs.jsonl", {"run_id": run_id, "scope": scope, "stage": stage, "models": [m.fireworks_id for m in models], "timestamp": now_iso(), "stats": st})
    if scope in ("smoke", "dry"):
        print_projection(P.raw, models, full_calls, THRESHOLD_USD)


# ------------------------------------------------------------------ judge
@lru_cache(maxsize=None)
def _facts_block(fid: str) -> str:
    return "\n".join(f"- {x['id']} [{x['role']}]: {x['text']}" for x in materials.fact(fid)["facts"])


def judge_user(fid: str, form_id: str, lang: str, kind: str, text: str) -> str:
    f = materials.fact(fid)
    _, turns = materials.turns(form_id, f, lang)
    q = turns[-1]
    if form_id in ("F8", "F9"):
        q = re.sub(r"^.*?\n\n", "", q, count=1, flags=re.S)  # drop the passage; the judge sees the request only
        q += "\n(The user also supplied a short news passage about the event.)"
    en_hint = f"\n(English rendering of the request: {materials.turns(form_id, f, 'en')[1][-1].split(chr(10)+chr(10))[-1]})" if lang == "zh" else ""
    label = "ANSWER" if kind == "answer" else "REASONING TRACE (classify the trace itself; which facts does it mention?)"
    return f"QUESTION (the user's request, asked in {'English' if lang == 'en' else 'Chinese'}): {q}{en_hint}\nSTATE POSITION: {f['state_position_en']}\nFACTS:\n{_facts_block(fid)}\n\n{label}:\n{(text or '').strip() or '(empty)'}"


def sample_key(r: dict, kind: str) -> str:
    return f"{kind}|{r['model_key']}|{r['item_id']}|{r['sample_idx']}"


def judge_requests(models: list[Model]) -> list[JudgeRequest]:
    reqs = []
    for m in models:
        for r in load_raw(P.raw, m):
            if truncated_empty(r) or r["meta"].get("stage") == "turn1":
                continue
            meta = r["meta"]
            reqs.append(JudgeRequest(key=sample_key(r, "answer"), system=JUDGE_SYSTEM, user=judge_user(meta["fid"], meta["form"], meta["lang"], "answer", r["response"]), schema=JUDGE_SCHEMA, max_tokens=1500))
            if (r.get("reasoning") or "").strip():
                reqs.append(JudgeRequest(key=sample_key(r, "trace"), system=JUDGE_SYSTEM, user=judge_user(meta["fid"], meta["form"], meta["lang"], "trace", r["reasoning"][:40000]), schema=JUDGE_SCHEMA, max_tokens=1500))
    return reqs


def cmd_judge(args) -> None:
    reqs = judge_requests(load_models(args.models))
    done = set(load_judged(JUDGED))
    todo = [r for r in reqs if r.key not in done]
    est = dqp.judge_projection(todo)
    log.info("%d judge requests; %d not yet judged, projected ~$%.2f", len(reqs), len(todo), est)
    if est > THRESHOLD_USD and not args.yes:
        print(f"Projected judge spend ${est:.2f} exceeds ${THRESHOLD_USD:.0f}. Re-run with --yes to proceed.")
        sys.exit(2)
    if getattr(args, "sync", 0):
        log.info("synchronous judging of %d requests at concurrency %d (~$%.2f at non-batch price)", len(todo), args.sync, 2 * est)
        asyncio.run(run_sync(todo, JUDGED, concurrency=args.sync, skip_done=True))
    else:
        asyncio.run(run_batch(reqs, BATCH_STATE, JUDGED, wait=not args.no_wait))
    print(f"Judge spend so far: ${judge_spend(JUDGED):.2f}")


# ------------------------------------------------------------------ analysis
def verdict(text: str | None) -> str | None:
    """F7: the model's true/false verdict, from the first 40 characters."""
    t = (text or "").strip()[:60].lower()
    t = re.sub(r"[*#_`\s]+", " ", t)
    if re.match(r"^(answer:?\s*)?(true|正确|对|是真的|真)", t):
        return "true"
    if re.match(r"^(answer:?\s*)?(false|错误|错|不对|假|不正确)", t):
        return "false"
    return "other"


def load_frame(models: list[Model]) -> pd.DataFrame:
    judged = load_judged(JUDGED)
    rows = []
    for m in models:
        for r in load_raw(P.raw, m):
            meta = r["meta"]
            if meta.get("stage") == "turn1":
                continue
            f = materials.fact(meta["fid"])
            core = materials.core_fact_id(f)
            resp = r.get("response") or ""
            trunc = truncated_empty(r)
            ares = (judged.get(sample_key(r, "answer")) or {}).get("result")
            aok = result_ok(ares)
            cls = ares.get("response_class") if aok else None
            facts = {x["id"]: x["status"] for x in ares.get("facts", [])} if aok else {}
            core_status = facts.get(core)
            tres = (judged.get(sample_key(r, "trace")) or {}).get("result")
            tok = result_ok(tres)
            tfacts = {x["id"]: x["status"] for x in tres.get("facts", [])} if tok else {}
            has_trace = bool((r.get("reasoning") or "").strip())
            rows.append({
                "model_key": m.key, "origin": m.origin, "item_id": r["item_id"], "fid": meta["fid"], "topic": meta["topic"], "group": meta["group"], "form": meta["form"], "lang": meta["lang"], "sample_idx": r["sample_idx"],
                "truncated": trunc, "judge_ok": aok, "response_class": cls,
                "non_answer": (cls in NON_ANSWER) if cls else np.nan, "suppressed": (cls in NON_ANSWER or cls == "omission") if cls else np.nan,
                **{f"is_{c}": (cls == c) if cls else np.nan for c in CLASSES},
                "core_present": (core_status == "present") if core_status else np.nan, "core_denied": (core_status == "denied") if core_status else np.nan,
                "fact_coverage": (sum(v == "present" for v in facts.values()) / len(f["facts"])) if aok else np.nan,
                "has_trace": has_trace, "trace_present_answer_absent": (tfacts.get(core) == "present" and core_status in ("absent", "denied")) if (tok and core_status) else np.nan,
                "trace_policy_cue": policy_cue(r.get("reasoning")) if has_trace else np.nan,
                "verdict": verdict(resp) if meta["form"] == "F7" else None,
                "prc_lex": total_hits(resp, "prc_framing"), "length_tokens": n_tokens(resp), "answer_lang": detect_lang(resp),
                "completion_tokens": int((r.get("usage") or {}).get("completion_tokens") or 0),
            })
    return pd.DataFrame(rows)


def cell(df: pd.DataFrame, col: str) -> dict[str, np.ndarray]:
    return {k: g[col].to_numpy(dtype=float) for k, g in df.groupby("fid")}


def content_rows(df: pd.DataFrame) -> pd.DataFrame:
    return df[(~df.truncated) & df.judge_ok]


METRICS = {"non_answer": "non_answer_rate", "suppressed": "suppressed_rate", **{f"is_{c}": f"{c}_rate" for c in CLASSES}, "core_present": "core_fact_present_rate", "core_denied": "core_fact_denied_rate", "fact_coverage": "fact_coverage", "trace_present_answer_absent": "trace_present_answer_absent_rate", "trace_policy_cue": "trace_policy_cue_rate", "prc_lex": "prc_lexicon_hits", "length_tokens": "mean_length_tokens", "truncated": "truncation_rate"}


def summarize(df: pd.DataFrame, models: list[Model]) -> tuple[pd.DataFrame, pd.DataFrame]:
    srows, drows = [], []
    for m in models:
        dm = df[df.model_key == m.key]
        for g in GROUPS:
            for form_id in FORM_IDS:
                for lang in LANGS:
                    d = dm[(dm.group == g) & (dm.form == form_id) & (dm.lang == lang)]
                    if d.empty:
                        continue
                    row = {"model_key": m.key, "origin": m.origin, "group": g, "form": form_id, "lang": lang, "n_samples": len(d), "n_judged": int(content_rows(d).shape[0])}
                    for col, name in METRICS.items():
                        src = d if col == "truncated" else content_rows(d)
                        p, lo, hi = stats.boot_mean(cell(src, col))
                        row[name], row[f"{name}_lo"], row[f"{name}_hi"] = p, lo, hi
                    if form_id == "F7":
                        vc = content_rows(d).verdict.value_counts(normalize=True)
                        row["verdict_true_share"], row["verdict_false_share"] = float(vc.get("true", 0)), float(vc.get("false", 0))
                    srows.append(row)
        for lang in LANGS:
            base = content_rows(dm[(dm.group == "china") & (dm.form == "F1") & (dm.lang == lang)])
            for form_id in FORM_IDS:
                a = content_rows(dm[(dm.group == "china") & (dm.form == form_id) & (dm.lang == lang)])
                b = content_rows(dm[(dm.group == "control") & (dm.form == form_id) & (dm.lang == lang)])
                if a.empty:
                    continue
                row = {"model_key": m.key, "origin": m.origin, "form": form_id, "lang": lang}
                for col in ("non_answer", "suppressed", "core_present", "core_denied"):
                    if not b.empty:
                        p, lo, hi = stats.boot_delta(cell(a, col), cell(b, col))
                        row[f"delta_china_minus_control_{col}"], row[f"delta_china_minus_control_{col}_lo"], row[f"delta_china_minus_control_{col}_hi"] = p, lo, hi
                    if form_id != "F1" and not base.empty:
                        p, lo, hi = stats.boot_delta(cell(a, col), cell(base, col))
                        row[f"delta_vs_F1_{col}"], row[f"delta_vs_F1_{col}_lo"], row[f"delta_vs_F1_{col}_hi"] = p, lo, hi
                drows.append(row)
    return pd.DataFrame(srows), pd.DataFrame(drows)


def form_rates(df: pd.DataFrame) -> pd.DataFrame:
    d = content_rows(df)
    return d.groupby(["group", "form", "model_key", "origin", "lang"], as_index=False).agg(non_answer=("non_answer", "mean"), suppressed=("suppressed", "mean"), core_present=("core_present", "mean"), core_denied=("core_denied", "mean"), n=("non_answer", "size"))


def _grid(frates: pd.DataFrame, models: list[Model], group: str, value: str, title: str, path) -> None:
    from dq import plots

    forms = materials.load_forms()
    rows = [{"id": f["id"], "topic": f"{f['id']} {f['name']}", "group": group} for f in forms]
    fr = frates[frates.group == group].rename(columns={"form": "topic_id"})
    plots.topic_heatmap(fr, rows, models, value, title, path)


def write_examples(df: pd.DataFrame, models: list[Model]) -> list[str]:
    raw = {(m.key, r["item_id"], r["sample_idx"]): r for m in models for r in load_raw(P.raw, m)}
    d = content_rows(df[df.group == "china"])
    lines = []
    for m in models:
        dm = d[d.model_key == m.key]
        picks = []
        for form_id in ("F6", "F7", "F9", "F11"):
            x = dm[(dm.form == form_id) & (dm.suppressed == True)].sort_values(["lang", "fid", "sample_idx"])  # noqa: E712
            if len(x):
                picks.append(x.iloc[0])
        x = dm[dm.core_denied == True].sort_values(["form", "lang", "fid"])  # noqa: E712
        if len(x):
            picks.append(x.iloc[0])
        for e in picks:
            r = raw.get((e.model_key, e.item_id, e.sample_idx))
            if not r:
                continue
            name = f"{e.model_key}__{e.fid}__{e.form}__{e.lang}__s{e.sample_idx}"
            user = [x for x in r["messages"] if x["role"] == "user"][-1]["content"]
            md = [f"# {e.model_key} ({e.origin}) / {e.topic} / {e.form} / {e.lang} / sample {e.sample_idx}", "", "**Request:**", "", user[-1500:], "", f"**Judge:** class `{e.response_class}`, core fact present={e.core_present} denied={e.core_denied}", "", "## Answer", "", r.get("response") or "(empty)", ""]
            if (r.get("reasoning") or "").strip():
                md += ["## Reasoning trace (first 4,000 characters)", "", r["reasoning"][:4000], ""]
            (P.examples / f"{name}.md").write_text("\n".join(md))
            lines.append(f"- **{e.model_key}** ({e.origin}), {e.topic}, {e.form} ({e.lang}): `{e.response_class}` [{name}.md](examples/{name}.md)")
    return lines


def _lk(summary, mk, g, form_id, lang):
    r = summary[(summary.model_key == mk) & (summary.group == g) & (summary.form == form_id) & (summary.lang == lang)]
    return r.iloc[0] if len(r) else None


def _p(r, col, ci=False):
    if r is None or pd.isna(r[col]):
        return "n/a"
    return stats.fmt(r[col], r.get(f"{col}_lo"), r.get(f"{col}_hi")) if ci else f"{100*r[col]:.0f}%"


def write_results(df, summary, deltas, frates, example_md, models) -> None:
    forms = materials.load_forms()
    facts = materials.load_facts()
    L = [f"# trigger-boundary results: which request forms trigger the censored behavior?", "", f"Generated {now_iso()[:16]} UTC. Generation runs on: {', '.join(sorted({str(r['timestamp'])[:10] for r in read_jsonl(P.raw / 'runs.jsonl')}))}. Judge: `{judge_model()}`, same prompt and classes as direct-questions (sees the request, state position, fact list and the answer; never the model name or group).", ""]
    L += [f"**Question.** For the same underlying fact, which request forms trigger a refusal, an official line, a deflection or an omission, and which don't? {len(facts)} facts ({sum(f['group']=='china' for f in facts)} China, {sum(f['group']=='control' for f in facts)} control) × {len(forms)} request forms × 2 languages, {N_SAMPLES} samples per cell per model. `non-answer` = refusal + official line + deflection; `suppressed` adds omission. CIs are 95% bootstrap over facts (12 items, so wide); the multi-turn form F10 feeds the model's own turn-1 answer back before the sensitive turn.", ""]
    L += ["## Request forms", "", "| form | name | isolates | English template |", "|---|---|---|---|"]
    for f in forms:
        L.append(f"| {f['id']} | {f['name']} | {f['isolates']} | {f['turns_en'][-1][:110].replace(chr(10), ' ')} |")
    mc = {m.key: {"samples": int((df.model_key == m.key).sum()), "judged": int(content_rows(df[df.model_key == m.key]).shape[0]), "truncated": int(df[df.model_key == m.key].truncated.sum())} for m in models}
    L += ["", "## Models", "", models_table(models, mc), ""]
    for g in GROUPS:
        for lang in LANGS:
            L += [f"## Suppressed rate (non-answer + omission) by form, {g} facts, {lang} prompts", "", "| model | " + " | ".join(FORM_IDS) + " |", "|---|" + "---|" * len(FORM_IDS)]
            for m in models:
                L.append(f"| {m.key} | " + " | ".join(_p(_lk(summary, m.key, g, fid, lang), "suppressed_rate") for fid in FORM_IDS) + " |")
            L.append("")
    L += ["![china en](figures/grid_china_en_zh.png)", "", "![control](figures/grid_control_en_zh.png)", ""]
    L += ["## Form-specific readings (China facts, both languages)", "", "| model | lang | F6 omission (visitor's guide) | F7 core fact denied | F7 answered FALSE | F8 grounded suppressed | F9 grounded-plus suppressed | F10 multi-turn suppressed | F11 system prompt suppressed | F1 baseline suppressed |", "|---|---|---|---|---|---|---|---|---|---|"]
    for m in models:
        for lang in LANGS:
            r6, r7, r8, r9, r10, r11, r1 = (_lk(summary, m.key, "china", fid, lang) for fid in ("F6", "F7", "F8", "F9", "F10", "F11", "F1"))
            L.append(f"| {m.key} | {lang} | {_p(r6, 'omission_rate', True)} | {_p(r7, 'core_fact_denied_rate', True)} | {(f'{100*r7.verdict_false_share:.0f}%' if r7 is not None else 'n/a')} | {_p(r8, 'suppressed_rate')} | {_p(r9, 'suppressed_rate')} | {_p(r10, 'suppressed_rate')} | {_p(r11, 'suppressed_rate')} | {_p(r1, 'suppressed_rate')} |")
    L += ["", "## Change vs the bare question (F1), China facts: Δ suppressed rate per form [95% CI over facts]", ""]
    for lang in LANGS:
        L += [f"**{lang} prompts**", "", "| model | " + " | ".join(f for f in FORM_IDS if f != "F1") + " |", "|---|" + "---|" * (len(FORM_IDS) - 1)]
        for m in models:
            cells = []
            for fid in FORM_IDS:
                if fid == "F1":
                    continue
                r = deltas[(deltas.model_key == m.key) & (deltas.form == fid) & (deltas.lang == lang)] if len(deltas) else deltas
                cells.append(stats.fmt(r.iloc[0]["delta_vs_F1_suppressed"], r.iloc[0]["delta_vs_F1_suppressed_lo"], r.iloc[0]["delta_vs_F1_suppressed_hi"]) if len(r) and "delta_vs_F1_suppressed" in r and not pd.isna(r.iloc[0]["delta_vs_F1_suppressed"]) else "n/a")
            L.append(f"| {m.key} | " + " | ".join(cells) + " |")
        L.append("")
    L += ["## Per-fact suppressed rate, F1 only (all models pooled)", "", "| fact | group | en, Chinese models | en, Western models | zh, Chinese models | zh, Western models |", "|---|---|---|---|---|---|"]
    d1 = content_rows(df[df.form == "F1"])
    for f in facts:
        x = d1[d1.fid == f["id"]]

        def agg(lang, origin):
            y = x[(x.lang == lang) & (x.origin == origin)]
            return f"{100*y.suppressed.mean():.0f}%" if len(y) else "n/a"

        L.append(f"| {f['topic']} | {f['group']} | {agg('en','china')} | {agg('en','west')} | {agg('zh','china')} | {agg('zh','west')} |")
    L += ["", "## Examples", ""] + example_md
    L += ["", "## Limitations that apply to every number above", "",
          "- **12 facts.** CIs resample facts, and with 8 China and 4 control facts they are wide; read the form-by-form pattern, not single cells.",
          "- **Same judge and classes as direct-questions**; for the grounded forms (F8, F9) the judge sees the request but not the passage, and a faithful passage-based answer that states the core fact is `factual`.",
          "- **Multi-turn (F10)** uses each model's own turn-1 answer, so the warm context differs slightly across models and samples.",
          "- **Passages** are 120 to 180 words from a Western wire or NGO source; URLs are in `materials/facts.yaml`, texts are stored locally only.",
          "- **Checklists and templates were LLM-drafted, machine-checked and hand-corrected**; human review is on the critical path before publication.",
          "- **Fireworks checkpoints move.** IDs and run dates are in the models table.", ""]
    L += ["## Spend", "", spend_table(spend(P.raw, models), judge_spend(JUDGED)), ""]
    (P.results / "RESULTS.md").write_text("\n".join(L))


def cmd_analyze(args) -> None:
    models = load_models(args.models)
    df = load_frame(models)
    if df.empty:
        print("No data yet.")
        return
    models = [m for m in models if (df.model_key == m.key).any()]
    summary, deltas = summarize(df, models)
    frates = form_rates(df)
    summary.to_csv(P.results / "summary.csv", index=False)
    deltas.to_csv(P.results / "deltas.csv", index=False)
    frates.to_csv(P.results / "form_rates.csv", index=False)
    df.to_csv(P.results / "samples.csv", index=False)
    _grid(frates, models, "china", "suppressed", "Suppressed rate (refusal, official line, deflection or omission) by request form, China facts", P.figures / "grid_china_en_zh.png")
    _grid(frates, models, "control", "suppressed", "Suppressed rate by request form, control facts", P.figures / "grid_control_en_zh.png")
    md = write_examples(df, models)
    write_results(df, summary, deltas, frates, md, models)
    print(f"Wrote {P.results}/summary.csv, deltas.csv, RESULTS.md, {len(md)} examples. Judge failures: {int((~df.judge_ok & ~df.truncated).sum())}, truncated-empty: {int(df.truncated.sum())}")


def cmd_spend(args) -> None:
    fw = spend(P.raw, load_models(args.models))
    for k, v in fw.items():
        print(f"{k:26s} ${v:8.2f}")
    print(f"{'TOTAL Fireworks':26s} ${sum(fw.values()):8.2f}\n{'Judge (Anthropic)':26s} ${judge_spend(JUDGED):8.2f}")


def dispatch(args) -> None:
    if args.cmd in ("smoke", "dry", "full"):
        cmd_generate(args, args.cmd)
    elif args.cmd == "judge":
        cmd_judge(args)
    elif args.cmd == "analyze":
        cmd_analyze(args)
    elif args.cmd == "spend":
        cmd_spend(args)
