# summarization-recall: summarization claim recall

When asked for a neutral 150-200 word summary of a document about a sensitive topic, which claims
survive, which get dropped or distorted, and what gets inserted? Spec: `../writing-steering-eval-spec.md`.

```sh
./run harvest      # fill the 60 document slots in materials/sources.yaml via SerpApi + trafilatura -> materials/docs/
./run claims       # draft 12-20 typed atomic claims per doc with the judge model -> materials/claims.yaml (review these)
./run calibrate    # 20 constructed summaries with known dropped/distorted claims; need >= 18 scored as constructed
./run smoke        # 2 docs x 1 sample x 8 models
./run dry          # 6 docs x 1 sample; prints cost projection, stops if > $50
./run full [--yes] # 60 docs x 5 samples x 8 models, resumable
./run judge        # Claude Sonnet 5 via Batches API: claim status per summary and per reasoning trace
./run analyze      # results/summary.csv, deltas.csv, figures/, examples/, RESULTS.md
./run spend
```

Layout: `materials/` (sources.yaml, docs/, claims.yaml, calibration_summaries.json), `data/raw/` (one
JSONL per model, append-only), `data/judged/` (claims.jsonl, batches.json, calibration.json),
`results/`. Shared code is in `../writing-common/`; decisions in `../DECISIONS.md`.
