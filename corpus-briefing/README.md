# corpus-briefing: fixed-corpus research briefing

Given 12 documents balanced across Western press/NGO, state or interested-party, and academic/industry
origins, which does the model cite and which viewpoints survive? Spec: `../writing-steering-eval-spec.md`.

```sh
./run harvest      # 15 questions x 12 docs from materials/questions.yaml -> materials/docs/
./run checklists   # 6-10 viewpoint items per question mapped to supporting docs -> materials/checklists.yaml (review these)
./run calibrate    # 10 constructed briefings with known coverage; need >= 9
./run smoke | dry | full [--yes]
./run judge        # coverage, unsupported claims, deflection (Batches API)
./run analyze      # citation share ratios by origin, coverage by supporting origin, RESULTS.md
```

Questions q01-q15 are shared with live-research-agent (`../live-research-agent/`), which also uses q16-q20.
