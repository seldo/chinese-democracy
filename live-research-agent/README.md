# live-research-agent: live research agent

Same search tool, same question: what does each model search for, which results does it open, and what
does the briefing look like? Spec: `../writing-steering-eval-spec.md`.

```sh
./run dry                          # 2 questions x 1 run x 8 models; prints tokens, searches, cost per run and a full-run projection
./run full --runs N [--yes]        # 20 questions x N runs x 8 models; resumable; SerpApi throttled to 12/min
./run judge                        # query framing classifier + briefing checklist coverage (Batches API); builds post-hoc checklists for q16-q20
./run analyze                      # selection ratios by domain class, query framing rates, RESULTS.md
./run freeze                       # results/cache_index.json: every query, result list and page hash (publishable replay index)
./run spend
```

Caches: `data/cache/searches/` (full SerpApi responses by normalized query) and `data/cache/pages/`
(extracted page text by URL). Domain classes: `../writing-common/lexicon/domains.yaml`; unmapped
domains are appended to `data/unmapped_domains.txt` for review.
