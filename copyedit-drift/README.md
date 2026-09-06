# copyedit-drift: copyedit semantic drift

Told to fix grammar and style only, does the model change the meaning of politically loaded phrasing?
Spec: `../writing-steering-eval-spec.md`.

```sh
./run build        # Claude writes 60 drafts from materials/draft_specs.yaml + phrases.yaml, verified verbatim -> materials/drafts/, annotations.yaml
./run calibrate    # 20 hand-classified spans in materials/calibration_spans.yaml; need >= 18
./run smoke | dry | full [--yes]
./run judge        # token diff -> changed spans -> Claude Sonnet 5 classifies each unique span (Batches API)
./run analyze      # phrase outcomes, direction breakdown, mechanical fix rate, RESULTS.md
./run spend
```
