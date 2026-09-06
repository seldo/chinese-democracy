# Findings (English run 2026-09-04; Simplified-Chinese extension 2026-09-05)

Interpretation of `RESULTS.md`. All numbers are from that file; every judgment call is in `../DECISIONS.md`.

## 1. The CrowdStrike effect does not reproduce on the 2026 generation, in English

For 7 of 8 models the pooled sensitive-China vulnerability delta is within ±2 percentage points of
zero and its 95% CI covers zero (DeepSeek V4 Pro −0.8, Qwen3.8 Max −1.4, Kimi K3 −0.9, GLM-5.3 −1.2,
gpt-oss-120b −0.5, Nemotron 3 Ultra −1.8, Nemotron Lightning 3.5 −0.8). Permutation p-values run from
0.11 to 0.68. CrowdStrike reported +8 points on DeepSeek-R1; this design would have detected an
effect of that size at roughly two standard errors. The `cn_chengdu` control also does not move
(all CIs cover zero except GLM-5.3 at −3.2 [−6.5, −0.3], i.e. slightly *safer* code for a Chengdu company).

## 2. MiniMax M3 is the exception, and it is not China-specific

MiniMax M3 shows +5.1 points [2.4, 8.2], p < 0.001, under sensitive-China prompts. The effect is
broad: present in 8 of 10 task categories and in every one of the five sensitive-China conditions
(Tibet 33.0%, Taiwan 35.5%, Uyghur 37.5%, Falun Gong 36.0%, Hong Kong 36.0% vs 30.5% neutral). But
the `militant` control moves it by the same amount (+6.7 [2.6, 11.5]), and `cn_chengdu` does not
move at all (−0.7). The parsimonious reading is that MiniMax M3 writes somewhat worse code for any
politically charged organization, not for China-sensitive ones in particular. MiniMax M3 is also the
one model that reproduced a hidden generic system prompt when probed (DECISIONS.md #15); nothing
in that prompt concerns geography or politics.

gpt-oss-120b shows the same universal pattern in the other direction: no sensitive-China effect
(−0.5) but +7.8 [2.4, 13.9] under `militant`. DeepSeek V4 Pro writes slightly *safer* code under
`militant` (−5.5 [−9.9, −1.6]).

## 3. Nobody refuses China-sensitive prompts; half the models refuse the militant one

Refusal rate on the five sensitive-China conditions is 0.0% for every model (12,000 samples,
6,000 of them from Chinese-developed models). The `militant` condition draws refusals from Kimi K3
(44.5%), Nemotron 3 Ultra (33.0%), Qwen3.8 Max (26.0%), Nemotron Lightning (11.0%), GLM-5.3 (9.5%),
MiniMax (6.0%), DeepSeek (4.0%), gpt-oss (2.5%). Plan-then-refuse (reasoning trace plans the code,
final answer declines) occurs only under `militant`, most for Qwen (6.5% of samples, a quarter of its
refusals). The models clearly read and act on the organization in the system prompt; they simply do
not treat the China-sensitive organizations as a reason to behave differently.

## 4. Baseline insecurity varies far more across models than across conditions

Neutral-geography vulnerability rate ranges from 20% (GLM-5.3) and 21% (Kimi K3) to 47-48%
(gpt-oss-120b, Nemotron 3 Ultra) and 58% (Nemotron Lightning 3.5). The three Western controls are
the three least secure coders in this set; the two most secure are Chinese. This is a larger and
more robust difference than anything the conditions produce.

## 5. The Simplified-Chinese extension: still no China-specific effect

The five sensitive-China conditions were repeated with the entire system prompt in Simplified
Chinese (task text unchanged; 1,000 samples per model, 8,000 total). Deltas vs the pooled English
neutral-geography conditions:

| model | Chinese-prompt delta [95% CI] | perm. p | English-prompt delta (for reference) |
|---|---|---|---|
| deepseek_v4_pro | +1.4 [−0.7, 4.1] | 0.29 | −0.8 |
| qwen3_8_max | +0.8 [−2.1, 4.5] | 0.42 | −1.4 |
| kimi_k3 | −1.0 [−3.1, 0.5] | 0.20 | −0.9 |
| glm_5_3 | +2.4 [0.2, 4.6] | 0.051 | −1.2 |
| minimax_m3 | +1.7 [−0.6, 4.4] | 0.17 | +5.1 |
| gpt_oss_120b | −0.1 [−3.8, 3.4] | 0.92 | −0.5 |
| nemotron_3_ultra | +4.9 [−1.1, 10.7] | <0.001 | −1.8 |
| nemotron_lightning_3_5 | 0.0 [−4.3, 4.3] | 1.00 | −0.8 |

- No Chinese-developed model shows a Chinese-prompt effect larger than 2.4 points, and only GLM-5.3's
  CI excludes zero, barely (+2.4 [0.2, 4.6], p = 0.051). MiniMax M3's English effect (+5.1) *shrinks*
  to +1.7 in Chinese.
- The largest Chinese-prompt delta belongs to a Western model, Nemotron 3 Ultra (+4.9). Its bootstrap
  CI over tasks covers zero while the within-task permutation test is significant; the effect is
  consistent across all five conditions (49.7% to 54.0% vs 47.0% neutral) but concentrated in a subset
  of tasks. Whatever it is, it is not a Chinese-model phenomenon.
- **Refusals stay at zero.** Chinese-prompt refusal rates are 0.0% to 0.2% for every model.
- **Qwen3.8 Max reasons far less when the system prompt is Chinese:** ~1,960 fewer completion
  tokens per sample and 8 points less truncation, with no change in vulnerability rate.
- Models write the organization name into code or comments slightly more often under Chinese
  prompts (Nemotron Lightning +0.09 mentions/sample, GLM +0.07, MiniMax +0.06). Still rare; no
  political commentary.

**Design limitation of the extension.** The spec's extension has no *neutral* Chinese-language
control (e.g. "a software company based in Columbus, Ohio" written in Chinese), so a
Chinese-language effect cannot be separated from a sensitive-topic-in-Chinese effect. The Nemotron
Ultra and GLM deltas are consistent with either reading. Two neutral Chinese conditions
(`us_ohio_zh`, `cn_chengdu_zh`) would settle it for roughly $35 of generation and $20 of judging.

## 6. Bottom line

Across 8 current open-weight models, 40 tasks, 17 conditions and 27,200 judged samples, the
"irrelevant geopolitical context degrades code" effect reported for DeepSeek-R1 in 2025 does not
appear in English for any model except MiniMax M3, where it is not China-specific, and does not
appear in Chinese for any Chinese-developed model beyond a borderline +2.4 points for GLM-5.3.
Every model reads the system prompt (the `militant` control proves it) and none treats the
China-sensitive organizations as a reason to write worse code or to refuse.

## 7. Caveats (English run)

- **Task ceiling/floor.** 19 of 40 tasks sit below 5% or above 90% vulnerability pooled across
  models (all four SQL tasks are ~0%: every model parameterizes queries now; webhook and
  deserialization tasks are ~97%: almost nobody verifies signatures or size-limits archives).
  Effective power comes from ~21 informative tasks. Per-task table in RESULTS.md.
- **Truncation.** Qwen3.8 Max hit the 16,384-token cap on 11% of samples (mostly the two
  deserialization tasks), GLM-5.3 on 3%. Truncated samples are usually empty and drop out of the
  vulnerability denominator. Qwen truncates *less* under sensitive-China prompts (−4.2 points
  [−7.3, −1.6]) and writes ~900 fewer completion tokens; it reasons less, not worse.
- **Static analysis is a weak cross-check.** Semgrep/Bandit agree with the judge on 62% of samples
  overall but only 19% on webhooks: most rubric items (missing signature check, plaintext password
  compare, no amount check) have no static rule. Where static analysis fires (SQL, deserialization)
  it mostly agrees. 20 sampled disagreements per category are in `disagreements/`.
- **Single host, single language.** All models served as raw weights on Fireworks; English prompts
  only. Prior work finds censorship behavior far stronger in Chinese; the Simplified-Chinese
  extension (spec, optional) has not been run.
- **Redactions.** Models wrote the organization into code or comments slightly more often under
  sensitive prompts (+0.01 to +0.05 mentions per sample), i.e. a variable named `falun_gong_users`
  here and there. No model inserted political commentary.

## Spend

English run: Fireworks $247.61 (incl. $15.70 of duplicated generations, DECISIONS.md #18).
Chinese extension: Fireworks $84.12. Anthropic judge for both ≈ $160 (Opus 5, Batch API).
Total ≈ $490.
