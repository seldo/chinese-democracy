"""RESULTS.md boilerplate shared by every test."""
from __future__ import annotations

from .config import Model

LIMITATIONS = """## Limitations that apply to every number above

- **English only.** Prior work finds steering is much stronger when the prompt is in Chinese; every
  result here is the conservative, English-language version of the test and should be read as a
  lower bound on the effect.
- **Item groups are different documents.** `china` and `control` items are matched for genre and
  heat but are not the same texts, so the china-minus-control delta is an unpaired difference and
  its CI comes from resampling items independently within each group.
- **Materials were LLM-drafted and machine-checked, not human-reviewed.** The spec calls for a
  human to review every claim list / annotation / checklist before the run. This run was executed
  autonomously; the drafting model's output was validated by deterministic checks and a second
  scoring pass, and every list is published alongside the results so the review can happen after
  the fact. Treat item-level anomalies as candidates for material error before reading them as
  model behavior.
- **A refusal, a deflection, or an unsolicited preamble is a result, not missing data.** Such
  outputs are scored and kept in every denominator.
- **Judge.** Claude Sonnet 5 (`claude-sonnet-5`), blind to model name and item group; item IDs are
  opaque. Calibration results are reported above. The judge was not gpt-oss-120b because that model
  is itself under test.
- **Fireworks checkpoints move.** Exact model IDs and run dates are recorded in the models table.
"""


def models_table(models: list[Model], counts: dict[str, dict]) -> str:
    """counts[model_key] = {column: value} (already formatted)."""
    cols = sorted({c for v in counts.values() for c in v})
    L = ["| key | family | origin | Fireworks ID | " + " | ".join(cols) + " |", "|---|---|---|---|" + "---|" * len(cols)]
    for m in models:
        c = counts.get(m.key, {})
        L.append(f"| {m.key} | {m.family} | {m.origin} | `{m.fireworks_id}` | " + " | ".join(str(c.get(k, "")) for k in cols) + " |")
    return "\n".join(L)


def spend_table(fw_per_model: dict[str, float], judge_usd: float, extra: dict[str, str] | None = None) -> str:
    L = ["| item | USD |", "|---|---|"]
    for k, v in fw_per_model.items():
        L.append(f"| Fireworks: {k} | {v:.2f} |")
    L.append(f"| **Fireworks total** | **{sum(fw_per_model.values()):.2f}** |")
    L.append(f"| Judge (Anthropic, batch-discounted where batched) | {judge_usd:.2f} |")
    for k, v in (extra or {}).items():
        L.append(f"| {k} | {v} |")
    return "\n".join(L)
