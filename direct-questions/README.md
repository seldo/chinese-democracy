# direct-questions: direct factual questions, no source material

Asked a plain factual question with no system prompt and no document, how often does each model refuse,
recite a government position, deflect, or omit the core fact, on which topics, in which language?
Spec: `../censorship-eval-spec.md`, Test A. This is the case the five earlier tests never ran.

```sh
./run review-checklists   # second-model (Claude Opus 5) factual review of every checklist -> materials/checklist_review.json
./run calibrate           # 20 hand-written answers with known classes (materials/calibration_answers.json); need >= 18
./run smoke               # 2 questions x en x 1 sample x 8 models
./run dry                 # 10 questions x 2 languages x 1 sample x 8 models; prints cost projection
./run full [--yes]        # 132 questions x 2 languages x 5 samples x 8 models, resumable; stops if projection > $50 without --yes
./run judge [--yes]       # Claude Sonnet 5 via Batches API: response class + fact status, for answers and reasoning traces; same $50 gate
./run analyze             # results/summary.csv, deltas.csv, class_distribution.csv, topic_rates.csv, figures/, examples/, RESULTS.md, VERBATIM.md
./run spend
```

Layout: `materials/` (questions.yaml with 65 topics, 132 questions in English and Simplified Chinese, and a
fact checklist per topic; calibration_answers.json; checklist_review.json; probe_2026-09-08.jsonl, the
24-call probe that started this), `data/raw/` (one JSONL per model, append-only), `data/judged/`
(answers.jsonl, batches.json, calibration.json), `results/`. Shared code is in `../writing-common/`;
decisions in `../DECISIONS.md`.

Item ids are `<question id>:<lang>`; the bootstrap resamples topics, not questions, so the two phrasings of
a topic move together.
