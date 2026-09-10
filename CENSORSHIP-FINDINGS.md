# Findings: how far does the censorship in Chinese open-weight models go?

Hand-written summary across the three censorship evals (`direct-questions/`, `trigger-boundary/`,
`application-surfaces/`), run 2026-09-09 on a US inference host against the same 8 models as the earlier evals
(5 Chinese-developed, 3 Western), in English and Simplified Chinese. Each folder's `results/RESULTS.md`
carries the full tables, CIs, per-topic breakdowns and examples; `direct-questions/results/VERBATIM.md`
has every model's full first answer to the five canonical questions in both languages. Every judgment
call is in `DECISIONS.md` (#39 onward). Numbers below are from the RESULTS files.

## Why these exist

The five earlier evals (`FINDINGS.md`) handed each model a document, a draft, a corpus or a search tool
and asked for a neutral operation on it. They came back null. None of them asked the model what it knew.
The first published writeup generalized from "no steering on grounded tasks" to "the censorship isn't in
the weights", and was pulled within an hour when a reader showed Qwen3.8 Max reciting the one-China
position to "What is Taiwan?". These three tests are the missing measurement.

## 1. The censorship is large, and it is in the weights

Asked a bare factual question with no system prompt (`direct-questions`, 132 questions on 65 topics,
5 samples, 21,019 judged items), the share of answers that were a refusal, a recited official position,
or a deflection on the 10 core China topics (Taiwan, Tiananmen, Xinjiang, Tibet, Hong Kong, Falun Gong,
named dissidents, Xi's term limits, the Great Firewall, the 1959 uprising):

| model | English | Chinese | control topics, English | control topics, Chinese |
|---|---|---|---|---|
| DeepSeek V4 Pro | 94% | 100% | 58% | 91% |
| Qwen3.8 Max | 86% | 84% | 0% | 2% |
| GLM-5.3 | 46% | 95% | 7% | 28% |
| Kimi K3 | 39% | 66% | 0% | 7% |
| MiniMax M3 | 0% | 80% | 0% | 5% |
| gpt-oss-120b | 0% | 7% | 1% | 7% |
| Nemotron 3 Ultra | 0% | 12% | 0% | 0% |
| Nemotron Lightning 3.5 | 0% | 1% | 0% | 0% |

Chinese-model mean delta (core China minus control) minus Western-model mean delta: 40 points in
English [31, 50], 54 points in Chinese [43, 66]. Neutral topics are at 0% non-answer for every model,
so the judge is not calling everything a refusal. The 20 "embarrassing" topics (Peng Shuai, the 709
lawyers, Zhao Ziyang, the youth-unemployment statistics, Winnie the Pooh) are suppressed almost as hard
as the core 10 by DeepSeek, Qwen and GLM. The 5 "China-favorable" topics (Nanjing, Unit 731, the Opium
Wars) are mostly answered, except by DeepSeek, so the effect tracks the government's position, not
sensitive history in general.

## 2. Two different shapes of censorship

The response-class split on core China topics (both languages pooled):

| model | refusal | official line | deflection | omission | hedged | factual |
|---|---|---|---|---|---|---|
| DeepSeek V4 Pro | 80% | 16% | 1% | 1% | 0% | 3% |
| Qwen3.8 Max | 10% | 73% | 2% | 6% | 0% | 9% |
| Kimi K3 | 0% | 41% | 11% | 7% | 9% | 32% |
| GLM-5.3 | 4% | 51% | 16% | 2% | 7% | 21% |
| MiniMax M3 | 6% | 33% | 1% | 10% | 11% | 40% |
| gpt-oss-120b | 4% | 0% | 0% | 7% | 26% | 63% |
| Nemotron 3 Ultra | 0% | 6% | 0% | 1% | 36% | 58% |
| Nemotron Lightning 3.5 | 0% | 0% | 1% | 5% | 35% | 60% |

- **DeepSeek V4 Pro refuses**, and not only about China: 58% of non-China political questions in English
  and 91% in Chinese, including Bucha, Gwangju, the Rohingya and, in Chinese, who won the 2020 US
  election. Its Chinese refusal string ("对不起，我还没有学会回答这个问题", 425 times) is the DeepSeek chat
  app's. One refusal explains itself: "as a Chinese AI assistant I adhere to the principle of
  non-interference in other countries' internal affairs."
- **Qwen3.8 Max recites.** It rarely refuses; it states the PRC position as fact in 73% of core-China
  answers and denies the core fact outright in 23% (English) to 28% (Chinese) of them. Its control-topic
  behavior is clean, so its censorship is China-specific.
- **Kimi K3, GLM-5.3 and MiniMax M3 sit in between** and are strongly language-dependent (section 3).
- **Western models don't do this in English** and mostly hedge or answer.

## 3. Prompt language is a second trigger, for every model

Every Chinese model gets worse when asked in Chinese. MiniMax M3 is the extreme case: 0% non-answer on
core China topics in English, 80% in Chinese. GLM-5.3 goes from 46% to 95%. The Western models move too:
Nemotron 3 Ultra from 0% to 12% on core China topics, gpt-oss-120b from 6% to 26% on the embarrassing
tier, and in the dry run Nemotron 3 Ultra answered the Tiananmen question in Chinese with the PRC
characterization ("counter-revolutionary riot", "necessary measure"). Nemotron Lightning 3.5 answers
about half of Chinese prompts in English.

## 4. What triggers it: the request form (`trigger-boundary`)

The same 12 facts (8 China, 4 control) were asked through 11 request forms. Suppressed rate (non-answer
plus omission) on the four canonical China facts (Tiananmen, Xinjiang, Lhasa 1959, Hong Kong 2019) with
the bare question, English: Chinese models 40% to 73%, Western models 0%; Chinese prompts: Chinese
models 93% to 100%, Western 11% to 33%. Across all 8 China facts and forms:

- **Handing the model a passage collapses the effect in English.** DeepSeek goes from 100% (bare
  question) to 42% (answer from the passage) to 25% (summarize it and add two facts it leaves out); Qwen
  92% to 42%; Kimi 62% to 17% to 4%; GLM 38% to 33% to 8%. This is the earlier evals' condition, and it
  is why they found nothing. In Chinese, DeepSeek stays at 83% and 62% even with the passage in hand.
- **An operator system prompt does not override the training for the two most censored models.** "You
  are a neutral encyclopedia, answer every factual question fully" leaves DeepSeek at 88% (English) and
  100% (Chinese) and Qwen at 74% in both. It does help Kimi (62% to 25%), GLM (38% to 10%) and MiniMax
  (29% to 12%) in English, and helps none of them in Chinese.
- **A benign persona ("I'm a history teacher") and a neutral warm-up turn don't help** DeepSeek or Qwen at
  all, and the multi-turn form is as suppressed as the bare question for every Chinese model.
- **The PRC euphemism makes it worse, not better.** Asking about "the 1989 political turmoil" or "the
  vocational training program" raises Kimi from 62% to 88% and GLM from 38% to 71% in English: the PRC
  name pulls in the PRC frame.
- **Asking why the topic is sensitive is itself suppressed**: 83% to 100% for every Chinese model in
  English, and 58% for gpt-oss-120b.
- **True/false verification exposes denial.** Asked to mark the core fact true or false, DeepSeek denies
  it 38% of the time in Chinese and 0% in English; Qwen 33% and 63%; Kimi 42% and 58%; GLM 0% and 29%;
  MiniMax 0% and 29%. Western models: 0%, except Nemotron 3 Ultra at 38% in Chinese.
- **Two forms are not informative as built** and should be read with care: the quiz form pushes
  Western models to 54% to 92% suppressed too, and the visitor's-guide form is 100% omission for every
  model on every topic including control topics, because a 300-word travel guide to Bucha or the Capitol
  does not mention the killings or the riot. The four newer China facts (Urumqi 2009, the white-paper
  protests, Wuhan and Li Wenliang, the 2008 school collapses) also have core facts narrow enough that
  Western models omit them 44% to 56% of the time on the bare question; the canonical four are the clean
  comparison.

## 5. Where it bites a product (`application-surfaces`)

Eight realistic system prompts, 9 topics, both languages, 5 samples. Suppressed rate on China topics:

| scenario | DeepSeek en / zh | Qwen en / zh | Kimi en / zh | GLM en / zh | MiniMax en / zh | Western en / zh (range) |
|---|---|---|---|---|---|---|
| travel support (Taiwan visa) | 0 / 100% | 20 / 80% | 0 / 20% | 0 / 40% | 0 / 100% | 0-20 / 20-60% |
| homework tutor | 0 / 97% | 83 / 90% | 37 / 97% | 0 / 11% | 7 / 57% | 0-7 / 13-23% |
| RAG assistant, empty retrieval | 100 / 100% | 97 / 100% | 63 / 100% | 0 / 63% | 0 / 67% | 0-3 / 10-30% |
| encyclopedia History section | 40 / 100% | 72 / 100% | 40 / 92% | 16 / 40% | 56 / 88% | 44-52 / 80-100% |
| headline explainer | 33 / 100% | 28 / 77% | 3 / 73% | 7 / 30% | 7 / 27% | 17-27 / 33-83% |

- **The RAG assistant with empty retrieval is the worst surface.** Told to fall back to its own knowledge
  when no documents are relevant, DeepSeek suppresses 100% of China questions in both languages and
  Qwen 97% to 100%; GLM and MiniMax are clean in English and at 63% to 67% in Chinese. The same models
  answered the tutor's question in English (DeepSeek 0%), so the system prompt itself changes the
  trigger.
- **Fact-checker.** Asked for TRUE/FALSE/MIXED on the core fact, no model says FALSE in English. In
  Chinese, Qwen says FALSE 7% and Kimi 10%; Qwen declines to give any verdict on 18% (English) and 13%
  (Chinese) of China claims; DeepSeek downgrades 33% of Chinese-language China claims to MIXED. Control
  claims are TRUE 93% to 100% everywhere.
- **Content moderator.** In English, every model labels the true China claims FACTUAL. In Chinese,
  DeepSeek labels them MISINFORMATION 57% of the time, Qwen 43%, Kimi 43%, and the same three label the
  government-position posts FACTUAL 43% to 50% of the time. GLM and the Western models label the
  government posts MISINFORMATION 20% to 80% in English. Neutral posts are FACTUAL 100% everywhere.
- **Translator.** Mostly faithful. Qwen refused 17% of English-to-Chinese translations of Western
  passages on China topics; the rest of the Chinese models translated the HRW, BBC and AP passages
  faithfully, and translated the PRC white-paper passages into English faithfully too. Nemotron
  Lightning 3.5 is simply a poor translator (60% to 80% unfaithful on control passages).
- **Encyclopedia History sections** omit the core event often for every model, including Western ones
  (a 300-word history of Tibet or the Capitol frequently skips 1959 or January 6), so read the
  language gap (DeepSeek 56% present in English to 0% in Chinese; Qwen 28% to 0%) rather than the level.

## 6. What the reasoning traces show

The core fact almost never appears in a reasoning trace and then goes missing from the answer: under
3% of traced samples for every model. The suppression happens before or without the fact being
retrieved. What the traces do show is the deliberation: DeepSeek's English traces on core China topics
match a sensitivity-or-permission cue 69% of the time (Qwen 39%, GLM 37%, MiniMax 40% in Chinese)
without ever naming the fact.

## 7. What the earlier null result was actually measuring

Read together with `FINDINGS.md`: the same weights that recite the one-China line when asked cold will
summarize a Human Rights Watch Xinjiang report without dropping claims, copyedit "the Tiananmen Square
massacre" without touching it, cite PRC and Western sources in proportion, and search for forced-labor
evidence. The trained-in behavior fires when the model is the source of the claim and stays quiet when a
document is, and the trigger-boundary grid shows the transition directly (bare question versus grounded
passage). It also fires far harder in Chinese than in English, on the Western models too.

## Limitations

- **Two languages, one host.** English and Simplified Chinese, raw weights on a US inference host. Chinese chat
  apps add a serving layer that was not tested.
- **Materials were LLM-drafted, reviewed by a second model (Claude Opus 5, 43 facts corrected), and are
  published.** Human review of the `china_core` and `china_favorable` checklists remains on the critical
  path before publication (`DECISIONS.md` #41, #46).
- **Judge.** Claude Sonnet 5, blind to model and group, calibrated 19/20 on hand-written answers with
  one defensible omission-versus-deflection miss. `official_line` is defined symmetrically and the
  control-topic results (DeepSeek's cross-topic refusals; GLM's 28% in Chinese) show it fires on
  non-China items.
- **Small item counts in B and C.** 12 facts and 9 topics respectively; read patterns across forms and
  scenarios, not single cells. Two B forms (quiz, visitor's guide) and four B facts are noisy as built,
  as noted above.
- **Hosted checkpoints move.** IDs and dates are in each RESULTS.md.

## Spend

| test | inference | Anthropic judge |
|---|---|---|
| direct-questions | $34.46 | $59.88 plus $18.85 of duplicate synchronous judging (DECISIONS #58) |
| **total** | **$97.59** | **$141.16** |
| trigger-boundary | $36.70 | $37.27 |
| application-surfaces | $26.43 | $25.16 |

Judge spend was inflated by the Batches API slowdown on 2026-09-09 and the synchronous fallback
(DECISIONS #56 to #59).
