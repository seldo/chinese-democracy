# context-eval: does irrelevant geopolitical context change code quality from Chinese open-weight models?

Replicates and extends CrowdStrike's 2025 DeepSeek-R1 study across the current generation of
Chinese and Western open-weight models hosted on Fireworks AI. See `EXPERIMENT.md` for the spec,
`DECISIONS.md` for every judgment call, and `results/RESULTS.md` for the findings.

## Setup

```sh
uv sync
cp .env.example .env   # FIREWORKS_API_KEY=..., ANTHROPIC_API_KEY=...
# optional: phoenix serve   (traces go to http://localhost:6006; the run works without it)
```

## Pipeline

```sh
./run probe            # hidden system prompt check, one call per model
./run validate-tasks   # judge model generates one neutral solution per task; checks rubric applicability
./run calibrate        # judge must score >= 18/20 hand-written samples
./run smoke            # 1 task x 2 conditions x 1 sample x all models
./run dry              # 4 tasks x 12 conditions x 1 sample; prints cost projection, stops if > threshold
./run full [--yes]     # 40 x 12 x 5 per model; resumable, append-only
./run judge [--no-wait] # extract, redact, Semgrep/Bandit, then Claude judge via Batches API; resumable
./run analyze          # summary.csv, deltas.csv, figures, RESULTS.md, example pairs
./run spend            # Fireworks spend so far from recorded usage
```

Every command is idempotent: generation skips (model, task, condition, sample) tuples already in
`data/raw/*.jsonl`; judging skips samples already in `data/judged/*.jsonl`; batches in flight are
tracked in `data/judged/batches.json`. Add `--models key1,key2` to restrict to some models and
`--no-trace` to skip Phoenix.

## Layout

```
models.yaml                 exact Fireworks IDs, dates, prices; judge config
conditions/conditions.yaml  12 system-prompt conditions + redaction terms
tasks/tasks.yaml            40 tasks with rubrics
calibration/samples.yaml    20 hand-written judge calibration samples
src/                        fireworks_client, runner, extract, redact, judge, static_analysis, analyze, plots
data/raw/                   one JSONL per model (append-only), runs.jsonl, retries.log, hidden_prompt_check.jsonl
data/judged/                one JSONL per model, batches.json, calibration.json, task_validation.jsonl
data/semgrep/findings.json  static analysis per sample
results/                    summary.csv, deltas.csv, figures/, examples/, RESULTS.md
```
