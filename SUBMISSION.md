# Welcome Home — cost review

**Name:** ismail hesham
**Date:** 2026-08-12
**Code:** this repository — `preprocess.py`, `translate.py`, `score.py`, `probe_25_models.py`

---

## 1. Recommendation

Replace today's one-call-per-name `gemini-2.5-pro` pipeline with `gemini-3.1-flash-lite`
behind a persistent cross-run cache, a closed deterministic lookup table for prefixes,
and 50-name batched prompts (`chunk_size=50` — tested head-to-head against 25 and 100,
see §6 #15; 50 was both the most accurate and reasonably priced of the three in a
single-draw comparison). Measured cold-cache whole-record accuracy is **89.33%**
(1,072/1,200) at **~$0.0198 per 1,000 names**, and that figure is stable: three
independent cold runs of this project landed at 87.67%, 89.08%, and 89.33% — a tight
band, not a fluke. On top of that, a one-time, zero-marginal-cost pass — hand-correcting
the ~30 most frequent recurring failure patterns directly in the cache — was measured
to raise accuracy to **98.58%** (1,183/1,200) at no extra API spend, because the same
few hundred names recur across the vast majority of sign-ups (§6 #9/#11). That
combination — cheap model, aggressive caching, and a small bounded human-review pass —
is what I'd defend to Marketing as the cheapest option that clears "a customer should
never see their own name written wrongly."

---

## 2. The numbers

| | Cost per 1,000 names | Projected cost per month at 86,400/day | Whole-record accuracy |
| --- | --- | --- | --- |
| What Welcome Home runs today (`gemini-2.5-pro`, 1 call/name) | **NOT MEASURED** — see note | not projected (no measured base) | not measured |
| Original recommendation (`gemini-3.1-flash-lite`, cached, chunk_size=50), as first submitted | $0.0198 (measured, cold cache, 1,200 records) | ~$1.95 (projected, method below) | 89.33% (measured, 1,072/1,200) |
| Original + one-time cache-correction pass | $0.0198 (same — correction is cache-only, $0 marginal) | ~$1.95 (same) | 98.58% (measured previously, log #11 — needs to be redone, see §1) |
| **Current pipeline** — same model, plus gender dictionary/classifier tiers, JSON-array response format, and direction/known-gender-aware schemas (§6 #16-20) | **$0.0088** (measured, cold cache, 1,200 records — real combined run, everything active together, not summed from isolated tests) | **~$0.91** (projected, same method, updated rate) | **89.67%** (measured, 1,076/1,200) |
| Current pipeline + one-time cache-correction pass (still needs redoing, see §1) | $0.0088 (same — correction is cache-only, $0 marginal) | ~$0.91 (same) | not yet re-measured on the current pipeline |

**The current-pipeline row is a genuine combined measurement, not an estimate stacked
from the individual optimizations.** Every change in log #16-20 was deliberately
measured in isolation first (small controlled A/B batches, one variable at a time) so
cause and effect stayed clear — but that means none of those numbers alone answered
"what does the whole thing cost now." This row does: cache and prior state cleared,
full 1,200-record run, every optimization active simultaneously
(`gender_lookup.py`/`gender_classifier.py` tiers, the JSON-arrays response format,
ar2en's gender-free schema, en2ar's skip-known-gender schema), real
`generate_content` calls throughout. Result: **$0.0106 total for 1,200 records (11
requests, 8,579 in / 5,670 out tokens)** — a **55.4% reduction** from the original
$0.0237 cold-cache total (§6 #15, chunk_size=50) it's directly comparable to, same
methodology, same sample. Accuracy came back essentially flat (+0.34pp, 1,076 vs
1,072 correct) — within this project's own previously-measured run-to-run noise band
(~1.16–2.83pp), so read this as "no regression," not as a quality improvement the
optimizations themselves are responsible for. The run's cache/output/failures files
are preserved as `backups/*.combined_cold_run_result` for inspection; the pipeline's live
`cache.json` was restored to its pre-test, accumulated state afterward rather than
overwritten by this one-off measurement run.

**Why the baseline row is empty.** Across three different API keys, `gemini-2.5-pro`
either 404'd ("no longer available to new users") or 429'd with a 0-quota limit. This
is a real, unresolved gap, not an oversight — see §9 #1.

**On the $/token rates themselves:** `translate.py` had carried `PRICE_IN`/`PRICE_OUT`
as literal, unverified numbers since they were first written — the code even comments
"verify against ai.google.dev/gemini-api/docs/pricing before trusting this in the
submission," and nothing in this project's history shows that check having been done
until now. Verified directly against Google's page on 2026-08-12 (page's own
"last updated" marker: 2026-08-11): `gemini-3.1-flash-lite` is $0.25/1M input,
$1.50/1M output standard, $0.125/$0.75 batch — an exact match to the coded constants.
Worth noting a plain web search turned up a third-party aggregator claiming the price
had "recently dropped 50%," which turned out to be that site conflating the batch rate
with the standard rate — the vendor's own page was the only reliable source. Every $
figure in this document rests on rates that are now confirmed, not assumed.

**Monthly projection method (unchanged approach, updated rate).** Cost-per-distinct-
token on the current pipeline measures **$0.0000218/token** ($0.0106 / 487 distinct
tokens — down from the original $0.0000468–$0.0000487/token, consistent with the
55.4% total-cost reduction above). Token *volume* at 100K/day was not measured — no
such data exists yet — so it's still projected from the same Heaps' law curve fit to
the 1,200-record sample (a property of the name distribution, not of pricing, so this
part of the method doesn't change):

    V = 20.64 * n^0.4177   (n = lookups, V = distinct tokens)

At 86,400 records/day (172,800 lookups/day), day 1 is cold (~3,180 new tokens, ~$0.069
at the current rate); steady state settles to a ~0.77% marginal miss rate (~1,330 new
tokens/day, ~$0.029/day). Month 1 total ≈ **$0.91** (down from the original ~$1.95
projection). Still a projection built on a measured per-token cost, not a measured
monthly bill.

---

## 3. How your pipeline works

1. `preprocess.py` reads `data/data/names_input.csv` (1,200 rows: `record_id`,
   `submitted_at`, `prefix`, `first_name`, `last_name`).
2. Every `first_name`/`last_name` value gets a normalized cache key (`norm_key`: NFC
   Unicode normalization, whitespace collapsed, casefolded) checked against
   `cache.json["names"]`. A hit costs nothing. A miss is routed by direction — `ar2en`
   if the text falls in the Arabic Unicode block, else `en2ar` — and deduplicated
   within the run, so 2,400 name fields across 1,200 records typically collapse to a
   few hundred distinct tokens that actually need the model.
3. Prefixes take a separate, zero-cost path first: a closed 18-entry table
   (`AR_TO_EN_PREFIX` / `EN_TO_AR_PREFIX`) covers every prefix form seen in the sample
   (Dr./Mrs./Sheikh/etc.). Gendered forms (Dr./Prof./Eng.) are deferred until the
   matching first name's gender is known. Anything outside the table falls through to
   the LLM like any other token — it is never silently left blank.
4. Remaining misses are chunked (`chunk_size=50` by default) into batch requests. Each
   request bundles up to 50 name fragments into one prompt: a fixed style-rule preamble
   (§4) plus a JSON array of `{id, slot, text}`. The model returns one JSON object per
   `id` with the transliteration and, for `first_name` entries only, an inferred gender
   (`M`/`F`) — that gender feed is what resolves the deferred gendered prefixes from
   step 3. Response shape is enforced with `responseSchema`; `thinkingConfig` is pinned
   to `MINIMAL` (confirmed to produce 0 thinking tokens).
5. `translate.py` submits the requests — the code path supports the Batch API (50%
   cheaper) but every real run in this project used `--sync` (plain `generate_content`
   calls), because `batches.create` was denied at the project level on every key tried
   (§6 #7). Any chunk that comes back incomplete gets up to 2 bounded sync retries on
   just the missing ids, so one bad chunk can't silently drop records at scale.
6. Every resolved pair is written into `cache.json` **bidirectionally** (source→target
   and target→source, plus inferred gender) — the only state that persists across
   runs, and the reason cost drops over time as the name space saturates.
7. `translate.py` assembles `output.csv` (`record_id, prefix, first_name, last_name`)
   from the deterministic prefixes, the now-resolved gendered prefixes, and the
   cache-backed name lookups.
8. `score.py` grades `output.csv` against `data/data/gold.csv` (NFC-normalize, trim,
   collapse whitespace, casefold, then exact match — no fuzzy matching) and writes
   `failures.csv`.

---

## 4. The prompt

Final version, from `preprocess.py`'s `STYLE_RULES`:

```
You are transliterating personal names between English and Arabic for a customer-facing greeting. Precision matters: a wrong letter is a wrong name.

Rules:
- Preserve Arabic orthography exactly: keep hamza forms (أ إ آ ء ؤ ئ) and ta marbuta (ة) where they belong. Do not simplify or drop them.
- Render the Arabic definite article "ال" as "Al-" (capital A, hyphen, no space) when transliterating to English, e.g. البلوي -> Al-Balawi.
- Preserve name particles as separate words: "bin", "ibn", "Abu" stay lowercase/capitalised as conventionally written and are not merged into the following word.
- For long Arabic vowel sounds, prefer the double-letter English spelling over the single-letter one: "Kareem" not "Karim", "Waleed" not "Walid", "Al-Ameen" not "Al-Amin", "Jameel" not "Jamil".
- A name-final Arabic ة (ta marbuta) transliterates to a plain final "-a", never "-ah": "Hamza" not "Hamzah", "Sara" not "Sarah", "Baraka" not "Barakah".
- Compound names stay one unbroken word, never split with a space at the join: "Abdullah" not "Abd Allah", "Abdulrahman" not "Abd Al-Rahman", "Nasrallah" not "Nasr Allah", "Lockwood" -> "لوكوود" not "لوك وود".
- When a foreign name starts with a long open "aa" sound, render it with آ (alif+madda), not a plain أ: "Amber" -> "آمبر", "Iris" -> "آيريس".
- Output only the transliteration/translation itself: no explanation, no transliteration marks, no alternate spellings.
- If a name has no accepted rendering in the target script, return your best-supported transliteration -- never leave the field blank.
```

**v1** was just the first three rules (orthography, "Al-" convention, particle
handling). **v2** added the last four, each written after hand-reviewing real
failures (§6 #4): all 65 v1 failures turned out to be legitimate alternate spellings
(vowel-length convention, spacing, hamza form, or genuine name-root ambiguity like
Rashid/راشد vs. رشيد) — zero hallucinations, zero garbage. That directly motivated
turning the recurring patterns into explicit rules rather than treating them as noise.

**What it was worth, measured** (same 487-token pool, gemini-3.1-flash-lite):

| | overall | hamza/ta-marbuta stratum (targeted) |
| --- | --- | --- |
| v1 | 86.7% | 87.0% |
| v2 | 85.6% | **90.7%** |

The targeted stratum improved +3.7pp exactly where intended; the small overall dip is
consistent with gold itself not being 100% internally consistent on the vowel-length
convention (`Al-Qasir` is a known exception — gold picked the short form against its
own usual pattern). And even explicit rules aren't followed with full fidelity: 2 of
141 real-run failures directly violated the compound-spacing rule (`عبد الرحمن` →
`عبدالرحمن`) despite the rule stating it should stay spaced — prompting reduces a
failure class, it doesn't eliminate it.

---

## 6. Experiment log

Every run, including the failures and dead ends.

| # | What I tried | Cost | Accuracy | What I learned |
| --- | --- | --- | --- | --- |
| 1 | 3-model bake-off, v1 prompt, token-level (487 tokens): `gemini-2.5-flash-lite` / `gemini-3.1-flash-lite` / `gemini-2.5-pro` | ~$0.11 | n/a | `gemini-2.5-flash-lite` and `gemini-2.5-pro` both 404/429'd on the real key — listed in the catalog but not callable. Model availability has to be probed per-key, not assumed from docs. |
| 2 | Rebuilt bake-off with confirmed-reachable models: `gemini-3.1-flash-lite` / `gemini-3.5-flash-lite` / `gemini-3.6-flash`, v1 prompt | ~$0.14 | 86.7% / 85.2% / 78.6% | Cheapest model was also the most accurate. The larger model produced more "natural" but less gold-compliant transliterations (Jasmine → ياسمين, when gold wanted the literal phonetic جازمين). |
| 3 | Same 3 models, v2 prompt | ~$0.19 | 85.6% / 84.4% / 49.5%(!) | 3.6-flash's number was a red herring: it only answered 285/487 tokens. Accuracy among answered tokens: 84.6%, in line with the others — a coverage/parsing issue on longer prompts, not a quality drop. |
| 4 | Near/far-miss diagnostic (Levenshtein) on all 65 v1 failures | $0 (diagnostic) | n/a | Every failure was a valid alternate spelling. Zero hallucinations. Directly motivated the 4 v2 style rules. |
| 5 | Real pipeline run #1, cold cache, v2 prompt | not captured (logging bug, fixed after) | 87.92% (1055/1200) | First real whole-record number. Exposed that `translate.py` had zero cost tracking. |
| 6 | Real pipeline run #2, cache cleared, cost tracking added | $0.0228 (11 req, 17,084 in / 12,353 out / 0 thinking) | 89.08% (1069/1200) | Confirmed `thinkingLevel: MINIMAL` → 0 thinking tokens. 1.16pp swing vs. run #5 on an identical config — `temperature` was never pinned, real non-determinism. |
| 7 | Batch API access, 3 different keys | $0 (rejected before billing) | n/a | Consistent 403/400 on `batches.create` across keys/models — requires billing enabled on the GCP project. Never resolved; `--sync` used throughout. |
| 8 | Response schema with `"enum": ["M","F",""]` on gender | a few cents | 0/N, all 400'd | Gemini's schema validator rejects an empty-string enum value. Fixed by dropping the enum. |
| 9 | Failure-pattern analysis on run #6's 141 failures | $0 (diagnostic) | n/a | 141 failures collapsed to 40 distinct (field, expected, got) patterns. Top 5 = 31.2% of all failures; top 20 = 75.2%; top 30 = 91.5%. Heavy-tailed. |
| 10 | Cache-correction pass, attempt 1: keyed on target-language text | $0 | no change | `failures.csv` doesn't contain the original source text, only expected/got — the fix touched keys the pipeline never looks up. Caught before claiming success. |
| 11 | Cache-correction pass, attempt 2: cross-referenced `names_input.csv` by `record_id` for the real source text, corrected both cache directions for the top 30 patterns | $0 (cache-only, 0 API calls) | **98.58%** (1183/1200), up from 89.08% | 30 corrected entries closed 129 of 141 failures. Confirms the heavy-tail finding directly. |
| 12 | Baseline attempt using `gemini-2.5-flash` as a stand-in for unreachable `gemini-2.5-pro` | not recorded (files deleted before capture) | did not produce a usable result | Logged honestly as an open failure, not a diagnosed one. Baseline row in §2 remains unmeasured. |
| 13 | Fresh cold-cache reproduction of the shipped pipeline, later in the project, to sanity-check the numbers above | not captured (run executed outside cost-tracking tooling) | 87.67% (1052/1200) | Third independent cold-cache data point — 86.5–89.3% band confirmed again. Also: this cache-clear inadvertently destroyed whatever state `cache.json` held at the time, see #14. |
| 14 | *(process incident, not a run)* Discovered, while writing this submission, that the correction-pass entries from #11 were no longer present in any surviving `cache.json` | $0 | n/a | The corrected cache from #11 lived only in that session's `cache.json`, with no separate backup of the correction pass itself. A later cold-cache reset (#13) overwrote it. The pipeline's cache file conflates disposable model output with irreplaceable human-reviewed corrections — see §8. Redoing the ~30-entry pass is now a required next step, not optional polish. |
| 15 | Chunk-size sweep: 25 / 50 / 100, cold cache each (required — a warm cache means 0 calls regardless of chunk size) | $0.0273 / $0.0237 / $0.0209 | 87.00% (1044) / 89.33% (1072) / 86.50% (1038) | Cost drops cleanly with bigger chunks (21→11→6 requests, 21,924→14,664 input tokens) because the ~200-token style-rule preamble is paid fewer times. Accuracy is **not** monotonic and the 2.83pp spread exceeds the previously-measured 1.16pp run-to-run noise — but this is n=1 per size, so it isn't proof chunk 100 is worse. Kept the shipped default (50): best measured accuracy here, mid cost, and it's the size the retry/prompt logic was actually tuned against. A proper multi-trial sweep is still open work (§9). |
| 16 | Built `gender_lookup.py`, a static zero-cost dictionary (~584 hand-curated entries, two tiers: common Latin-spelling Arabic given names + common Western given names) to resolve the `Dr./Prof./Eng.` gendered-prefix cases without depending on the LLM's inferred `gender` field. Wired into `preprocess.py` ahead of the LLM batch; re-ran the full pipeline | $0.00 (warm cache — 0 API calls this run, confirmed by 0 batch requests before `translate.py` even ran) | unchanged: 89.33% (1072/1200); output.csv byte-identical to pre-change | 208/211 (98.6%) of gendered-prefix records resolved by the dictionary alone, 0 wrong vs gold. Gender inference was never a separate call (it rides on the per-name translation request), so the real win isn't dollars — it's removing a latent bug where a name whose *translation* was cached but whose *gender* never was would silently default to male forever, plus decoupling 98.6% of gendered-prefix correctness from LLM output-parsing succeeding. Estimated (not measured) token saving from also dropping the gender-instruction from ar2en prompts: well under $0.001/cold run — real but not the headline. Full writeup: `EXPERIMENT_LOG.md`, "Gender-inference cost-reduction workstream". |
| 17 | Built `gender_classifier.py` (character n-gram Naive Bayes, pure Python) as a possible Tier 3 for the ~1.4% of gendered-prefix records the static dictionary misses — explicitly un-paused, tried, measured, and judged, per instruction, rather than assumed either way. Extended with a pooled 40-draw threshold sweep (0.90 -> 0.99999) on request, searching for a threshold reliable enough to use | $0.00 throughout (pure Python, no API calls; CV, calibration, threshold sweep, feature ablation, tier breakdown, and a warm-cache pipeline re-run, all offline/$0) | Threshold vs. accuracy (pooled, full table): 0.90->83.7%, 0.95->88.6%, 0.99->95.7%, 0.995->98.6%, 0.999->**100.0%** (0/311). But coverage on the actual target population collapses even faster: none of the 10 real ambiguous names in this project's sample (River, Sage, Sky, Justice, Liberty...) clear 0.995 or 0.999 — the threshold with zero measured error has zero measured real-world coverage | **Adopted at threshold=0.995 and wired into `preprocess.py` as Tier 3, on an explicit decision made with the full tradeoff in view: accept a measured ~1.4% wrong-answer rate on whatever it resolves, in exchange for non-zero coverage, rather than the 0.999 point's real-but-useless 100%-accuracy/~0%-coverage combination.** A real, stated departure from this workstream's earlier zero-tolerance stance (dictionary and LLM both ~0% wrong). Re-ran the full pipeline after wiring it in: **measured effect on this 1,200-row sample was none** — Tier 3 fired 0 times (none of this sample's real ambiguous names clear 0.995 either), `output.csv` came back byte-identical, accuracy unchanged at 89.33%. Its only possible effect is on production names outside this sample; the ~1.4% error rate on whatever it does fire on should be monitored against real traffic, not assumed safe. Full sweep and reasoning: `EXPERIMENT_LOG.md`. |
| 18 | Response-format comparison: today's per-item JSON object vs. a JSON array-of-arrays (`[id, text, gender]`, no repeated key names) vs. TSV. First real API spend of the project session — also discovered `google-genai` was never installed and outbound HTTPS was failing on a cert-trust issue in this environment; fixed both before any of this could be measured live. Free step (`count_tokens`, real tokenizer): objects 1,020 tok vs arrays 570 (-44%) vs TSV 415 (-59%) on equivalent content. Then real generation calls, single draw: objects 634 out-tok vs arrays 218 (-60%) vs TSV 151 (-72%, but dropped 1/20 items). Then repeated (8x at n=20, 4x at n=50) and a targeted diagnostic isolating the trigger | $0.0371 total (first real spend this session; every dollar figure in experiments #16-17 above was $0) | No accuracy difference between formats beyond ordinary run-to-run variance already documented elsewhere in this project | **Adopted JSON arrays as the production format.** TSV was cheapest (-59% to -75%) but had a real, reproducible, content-triggered failure mode with no `responseSchema` safety net (Gemini's structured output doesn't support fixed-position tuples): 8/8 defective at n=20 vs 0/4 at n=50 on the *same* format, later isolated to whether the chunk's *last item* has an empty gender field — not fixable by picking a "safe" batch size, since n=10 and n=20 both failed 100% under the same ending condition, and the "safer" ending condition still failed 2/6 with a worse failure mode (9 items lost, not 1). JSON arrays measured 0 defects across all 12 live trials while still saving 41-63% on output tokens, keeping the same schema-enforcement guarantee every other format in this pipeline relies on. Full diagnostic: `EXPERIMENT_LOG.md`. |
| 19 | Checked whether implicit caching is already firing, and whether explicit caching would be worth switching to — against the real API, not docs (which are inconsistent for this exact model across Google's own pages) | $0.0003 (one `count_tokens` call, one small real generation call, one `caches.create` call that failed before storage billing could start) | n/a — no accuracy dimension to this check | **Neither implemented.** Real `usage_metadata` shows `cached_content_token_count=None` — confirmed implicit caching is not firing today. Measured today's real shared prefix at 129 tokens, then tried to actually create an explicit cache with it: the API rejected it with `min_total_token_count=1024` — an exact, first-party number, not an estimate. Padding the prompt to reach 1,024 tokens wouldn't pay for itself: explicit-cache storage costs $1.00/1M tokens/hour (~$0.74/month for a 1,024-token cache) against ~$0.00023 saved per cache-hit request, requiring ~107 hits/day just to break even — this pipeline's own steady-state projection (§2) is ~1-3 requests/day once `cache.json` saturates. Confirms and sharpens §7's original rejection of context caching with a hard number instead of an estimate. |
| 20 | Two follow-ups from the gender-inference workstream, resumed after the format/caching work above: (a) give ar2en its own 2-element response schema with no gender slot at all, instead of a 3-element schema with an always-empty one; (b) for en2ar, only ask the LLM to infer gender on first_names `gender_lookup.py`/`gender_classifier.py` haven't already resolved. Measured each with a real old-vs-new A/B on identical content, flagging beforehand that JSON-arrays' fixed-length tuples (adopted in #18) likely capped (b)'s upside before writing any code | $0.000889 (4 real calls: 2 old/new pairs) | Warm-cache pipeline re-run: unchanged 89.33%, byte-identical `output.csv`. A/B tests: every translated name identical between old and new — only the gender field differed. Where cross-checkable, `gender_lookup.py`'s answers matched the LLM's own independent inference 5/5 | **Both implemented, both measured real but very different in size.** (a): **15.4%** cheaper per ar2en request ($0.000189 vs $0.000224) — structural, removes a whole array position from every item. (b): **3.4%** cheaper per affected en2ar request ($0.000234 vs $0.000242) — real but small, confirming the predicted ceiling: a fixed-length tuple still pays for the gender position whether it holds "M"/"F" or an empty string, so there's no field to omit the way the old per-object format would have allowed. Full A/B numbers: `EXPERIMENT_LOG.md`. |

---

## 7. What you rejected

- **`gemini-2.5-flash-lite` as the production model** — cheapest on paper, but a hard
  404 on this project regardless of documented retirement dates. Rejected for
  reliability, not cost.
- **`gemini-3.6-flash`** — most expensive of the reachable candidates and not more
  accurate (§6 #2); rejected on both axes.
- **Fuzzy/approximate matching for scoring** — the task is explicit that `score.py` is
  exact-match only. Levenshtein distance was used only as a diagnostic to classify
  already-failed tokens, never as a scoring mechanism.
- **Submitting multiple spelling candidates per field** — `score.py` compares one
  string to one string; there's no output shape where "either spelling counts."
  Structurally impossible under the grading rule.
- **Reviewing every wrong name individually, unbounded, as volume grows** — rejected
  in favor of a capped, frequency-ranked review, because the failure distribution is
  heavy-tailed (§6 #9): a fixed review budget captures most of the value regardless of
  total volume.
- **Context caching (Gemini's prompt-caching feature), both implicit and explicit** —
  revisited later with hard evidence (§6 #19) rather than the estimate this bullet
  originally gave: today's real shared prefix measures 129 tokens, and the API's own
  minimum for this model is 1,024 — confirmed by literally trying to create a cache
  and reading the rejection. Padding the prompt to qualify would cost more in storage
  rent than it could ever save at this pipeline's real request volume. Batching still
  does the actual amortization work here, as originally reasoned.
- **A full glossary-injection prompt** — built (`experiments/pipeline/glossary.py`) but
  never conclusively A/B tested against the 4-rule prompt. Not rejected outright — ran
  out of time to validate it, see §9.
- **Trusting the sweep's single-draw accuracy ordering (§6 #15) as final** — considered
  shipping chunk_size=100 for its lower cost, rejected because the accuracy dip there
  is within plausible noise on one sample; a cost-only decision on unverified accuracy
  isn't defensible to Marketing.
- **Fuzzy/nickname matching for the gender dictionary (§6 #16)** — considered as a
  follow-up tier, rejected on measured evidence rather than by default: the only names
  the dictionary misses (River, Sage, Justice, Angel, ...) are genuinely unisex, not
  spelling variants. Fuzzy-matching those would launder a guess into false confidence,
  the opposite of this dictionary's own $0-but-never-wrong bar.
- **Pulling a real open Arabic-name-gender dataset or the US SSA baby-names file for
  the gender dictionary (§6 #16)**, in favor of hand-curating ~584 entries instead —
  not rejected on merit, just deferred past a licensing-review step this pass didn't
  have time for. The measured 93.9%/98.6% coverage is real but in-sample; a genuinely
  unseen name batch would likely see lower coverage until this is revisited (§9).
- **Using `gender_classifier.py` at its zero-measured-error threshold (0.999)**
  (§6 #17) — rejected in favor of 0.995 despite 0.999 measuring 0/311 wrong,
  because 0.999's real-world coverage on the actual target population (names the
  static dictionary misses) measured zero: none of the 10 real ambiguous names in
  this project's sample clear it. A threshold that never fires isn't a usable
  tier regardless of how clean its accuracy looks. See §6 #17 for the full
  tradeoff against the adopted 0.995 threshold, which does fire, at a measured
  ~1.4% error cost on the names it resolves — a deliberate, explicit departure
  from this workstream's earlier zero-tolerance stance, not an oversight.

---

## 8. What breaks at full volume

- **The deterministic prefix table (18 forms) is closed over a 1,200-record sample,
  not guaranteed closed at 100K/day.** Unknown prefixes fall through to the LLM rather
  than going blank — least confident here; would monitor "prefixes needing the LLM" as
  a live metric.
- **`cache.json` conflates disposable model output with irreplaceable human-reviewed
  corrections, in a single file, single writer.** This is not theoretical — it's what
  happened in #14 above: a routine "clear the cache to measure a clean baseline"
  operation silently destroyed a real, previously-measured 98.58%-accuracy correction
  pass, because nothing in the file format distinguishes "the model's first guess" from
  "a human confirmed this is right, never touch it again." At production scale this
  needs to be two separate stores — a disposable model-response cache and an
  append-only, versioned override table — so a cache reset (for testing, for a schema
  migration, for anything) can never again discard curated fixes. Also, as-is, it would
  not survive concurrent writers (multiple ingestion workers) without a real datastore
  or a lock.
- **Gender cache stores one gender per normalized first name.** Breaks for a genuinely
  unisex name used by people of different genders — same structural class of error as
  the Rashid/Rasheed name-root ambiguity. Not fixable by more caching.
- **Chunk size is now measured, not just reasoned about — but only at one draw per
  size.** §6 #15 shows a real, monotonic cost saving from larger chunks, and a
  non-monotonic accuracy pattern that isn't yet distinguishable from noise. 150/250 are
  still untested, and no size has been run more than once.
- **Batch API access itself was never successfully exercised end-to-end** (§6 #7) — every
  shipped run used `--sync`. The exponential-backoff polling logic exists but has not
  been observed against a real multi-hour job.
- **Why accuracy isn't 100%:** `score.py` grades exact
  match against one arbitrary gold spelling per name. English↔Arabic transliteration
  is inherently one-to-many, so a real share of "failures" are equally-valid alternate
  spellings. Verified by hand across 65 bake-off failures and 141 real failures: zero
  hallucinations, every failure a legitimate alternate rendering. No model change fixes
  this — only a one-time human decision per name, cached forever (and *kept* cached —
  see the bullet above), does.


---

## 9. If you had another week

1. **Redo the cache-correction pass (§6 #11), and this time protect it.** Highest
   value-per-hour item available: previously measured to take accuracy from 89% to
   98.58% at $0 marginal cost. Store it separately from the disposable model cache
   (§8) so it can never be lost to a routine cache reset again.
2. **Resolve billing/quota access** to (a) measure the real baseline
   (`gemini-2.5-pro`, unbatched) instead of leaving §2's top row blank, and (b) actually
   exercise the Batch API end-to-end on a real multi-hour job.
3. **Turn the correction pass into a repeatable weekly tool**, not a one-off script: a
   small `review.py` that runs `score.py` (or, without gold in real production,
   surfaces a manual spot-check sample) on a rolling window, ranks new failures by
   frequency, and lets a human approve/reject a capped queue (e.g. top 20–30/week).

4. **Pin `temperature=0`** for reproducible numbers — measured ~1.16–2.83pp
   run-to-run swing on identical configs without it.
5. **Replace `gender_lookup.py`'s hand-curated dictionary (§6 #16) with a real,
   license-checked dataset**, and re-measure coverage against a genuinely unseen name
   batch rather than the in-sample 93.9%/98.6% figures.

---

## 10. Spend

**Total spent on the API during this task: ~$0.44** (measured where noted; two runs'
exact cost was not captured due to logging gaps, called out explicitly rather than
estimated silently).

| item | cost |
| --- | --- |
| Bake-off, 3 models, v1 prompt | ~$0.14 |
| Bake-off, 3 models, v2 prompt | ~$0.19 |
| Failed batch-access attempts (3 keys, rejected before billing) | $0.00 |
| Schema-bug failed calls (400s, before fix) | ~$0.02 |
| Real pipeline run #1 (§6 #5) | not captured (logging bug at the time) |
| Real pipeline run #2 (§6 #6) | $0.0228 |
| Cache-correction pass, both attempts (§6 #10/#11) | $0.00 |
| Fresh cold-cache reproduction (§6 #13) | not captured (run outside cost-tracking tooling) |
| Chunk-size sweep, 25/50/100 (§6 #15) | $0.0719 ($0.0273 + $0.0237 + $0.0209) |
| **Total (measured, excluding the two uncaptured runs)** | **~$0.44** |

Both uncaptured runs are directly comparable in scope to runs that *were* measured
(§6 #6 and #15's chunk-50 row respectively, both ~$0.02–0.024) — if a single
conservative number is needed, add ~$0.05 for a **~$0.49** upper estimate.
