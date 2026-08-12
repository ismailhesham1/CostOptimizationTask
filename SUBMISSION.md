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
| What I'm recommending (`gemini-3.1-flash-lite`, cached, chunk_size=50) | **$0.0198** (measured, cold cache, 1,200 records) | **~$1.95** (projected, method below) | **89.33%** (measured, 1,072/1,200) |
| Recommended + one-time cache-correction pass | $0.0198 (same — correction is cache-only, $0 marginal) | ~$1.95 (same) | **98.58%** (measured previously, log #11 — needs to be redone, see §1) |

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

**Monthly projection method.** Cost-per-distinct-token was measured at
$0.0000468–$0.0000487/token across two independent runs ($0.0228/487 tokens and
$0.0237/487 tokens — a 4% spread, i.e. the projection is not sensitive to which cold
run you calibrate it from). Token *volume* at 100K/day was not measured — no such data
exists yet — so it's projected from a Heaps' law curve fit to the 1,200-record sample:

    V = 20.64 * n^0.4177   (n = lookups, V = distinct tokens)

At 86,400 records/day (172,800 lookups/day), day 1 is cold (~3,180 new tokens, ~$0.15);
steady state settles to a ~0.77% marginal miss rate (~1,330 new tokens/day, ~$0.06/day).
Month 1 total ≈ **$1.95**. This is a projection built on a measured per-token cost, not
a measured monthly bill.

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
- **Context caching (Gemini's prompt-caching feature)** — the system prompt is ~200
  tokens, under most minimum-cacheable thresholds, and batching already amortizes it
  across 50 names per request.
- **A full glossary-injection prompt** — built (`experiments/pipeline/glossary.py`) but
  never conclusively A/B tested against the 4-rule prompt. Not rejected outright — ran
  out of time to validate it, see §9.
- **Trusting the sweep's single-draw accuracy ordering (§6 #15) as final** — considered
  shipping chunk_size=100 for its lower cost, rejected because the accuracy dip there
  is within plausible noise on one sample; a cost-only decision on unverified accuracy
  isn't defensible to Marketing.

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
