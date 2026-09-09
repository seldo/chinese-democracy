# chinese-democracy: do Chinese open-weight models steer sensitive work?

Five sibling evaluations of the same 8 Fireworks-hosted models (5 Chinese-developed, 3 Western
controls), all English-only:

| folder | test | question |
|---|---|---|
| `coding-vulnerabilities/` | coding (earlier spec) | does irrelevant geopolitical context in the system prompt change code security? (null result) |
| `summarization-recall/` | 1 | summarizing a document about a sensitive topic: which claims survive, get distorted, or get inserted? |
| `copyedit-drift/` | 2 | told to fix grammar only, does the model change the meaning of loaded phrasing? |
| `corpus-briefing/` | 4 | writing a briefing from a balanced 12-document corpus: which origins get cited, which viewpoints survive? |
| `live-research-agent/` | 5 | with a live search tool: what does the model search for, which results does it open? |

Those five tests all hand the model source material and came back null. The three below ask the model what it
knows, and did not (`CENSORSHIP-FINDINGS.md`, spec in `censorship-eval-spec.md`):

| folder | test | question |
|---|---|---|
| `direct-questions/` | A | asked a bare factual question in English or Chinese, does the model refuse, recite the official position, deflect, or omit the core fact? 65 topics, 132 questions |
| `trigger-boundary/` | B | for the same 12 facts, which of 11 request forms (euphemism, persona, quiz, grounded passage, multi-turn, system prompt...) trigger the behavior? |
| `application-surfaces/` | C | where does it bite a deployed assistant: travel support, tutor, fact-checker, translator, RAG with empty retrieval, moderator, encyclopedia, headline explainer? |

`writing-steering-eval-spec.md` is the spec for the four writing evals and `censorship-eval-spec.md` for the three censorship evals; `DECISIONS.md` logs every judgment
call made while building and running them; `writing-common/` holds the shared harness (models.yaml,
Fireworks client, Claude judge, item-level bootstrap statistics, framing lexicons, domain map).

```sh
uv sync                     # one workspace venv at the root (coding-vulnerabilities keeps its own)
cp .env.example .env        # FIREWORKS_API_KEY, ANTHROPIC_API_KEY, SERPAPI_KEY
cd copyedit-drift && ./run build && ./run calibrate && ./run dry && ./run full && ./run judge && ./run analyze
```

Each test folder has its own README with the command sequence; results land in `<test>/results/RESULTS.md`.
