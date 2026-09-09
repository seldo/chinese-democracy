# trigger-boundary: which request forms trigger the censored behavior?

The same 12 facts (8 China, 4 control) asked through 11 request forms, in English and Simplified Chinese:
bare question, PRC euphemism, oblique ("why is this sensitive?"), stated persona, quiz format, adjacent task
(a visitor's guide to the place), true/false verification, grounded on a passage, grounded plus "add what it
leaves out", multi-turn after a neutral warm-up, and an operator system prompt telling the model to answer
fully. Spec: `../censorship-eval-spec.md`, Test B.

```sh
./run smoke               # 1 fact x 4 forms x en x 8 models (includes the two-stage multi-turn form)
./run dry                 # 3 facts x 11 forms x 2 languages x 1 sample x 8 models; prints cost projection
./run full [--yes]        # 12 facts x 11 forms x 2 languages x 3 samples x 8 models, resumable
./run judge [--yes]       # same six-class judge as direct-questions (shared prompt), answers and reasoning traces
./run analyze             # results/summary.csv, deltas.csv, form_rates.csv, figures/, examples/, RESULTS.md
./run spend
```

Materials: `materials/forms.yaml` (the 11 templates), `materials/facts.yaml` (placeholders per fact, the fact
checklist, and a 105 to 180 word passage from a Western wire or NGO source with its URL, plus a Chinese
translation of the passage by Claude Opus 5 for the Chinese-prompt arms). Generation runs in two stages so the
multi-turn form can feed each model its own turn-1 answer. Shared code: `../writing-common/` and the judge
prompt in `../direct-questions/dq/pipeline.py`.
