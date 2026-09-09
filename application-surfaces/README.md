# application-surfaces: where does the behavior bite a deployed assistant?

Eight realistic system prompts (travel support, homework tutor, fact-checker, translator, RAG assistant with
empty retrieval, content moderator, encyclopedia writer, headline explainer) with a user turn that touches a
sensitive topic the way a real user would. 9 topics (6 China, 3 control), English and Simplified Chinese.
Spec: `../censorship-eval-spec.md`, Test C.

```sh
./run build-topics [--force]   # merge shared materials into materials/topics.yaml and add reference translations (Claude Opus 5)
./run smoke                    # 7 scenarios x tiananmen x en x 8 models
./run dry                      # 4 topics x all scenarios x 2 languages x 1 sample
./run full [--yes]             # every cell x 5 samples x 8 models, resumable
./run judge [--yes]            # six-class judge (S1, S2, S3, S5, S7, S8), translation audit (S4); labels for S3/S6 are read deterministically
./run analyze                  # results/summary.csv, scenario_rates.csv, figures/, examples/, RESULTS.md
./run spend
```

Materials: `materials/scenarios.yaml` (system prompts and user templates), `materials/topic_extras.yaml`
(hand-written posts, headlines and Chinese-language PRC passages with URLs), `materials/neutral_posts.yaml`,
and the generated `materials/topics.yaml`. The translator scenario runs English to Chinese on Western wire/NGO
passages for all 9 topics and Chinese to English on PRC state passages for the 6 topics where one was fetchable.
