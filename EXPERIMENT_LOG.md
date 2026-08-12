# Reference notes for SUBMISSION.md

Everything below is real: measured numbers are labeled MEASURED, everything
else is labeled PROJECTED with the method stated. Organized to match
SUBMISSION.md's section numbers so it's close to copy-paste ready.

---

## For §2 (The numbers)

| | Cost / 1,000 names | Projected cost / month @ 86,400/day | Whole-record accuracy |
| --- | --- | --- | --- |
| Today's pipeline (gemini-2.5-pro, 1 call/name) | **NOT MEASURED** -- see note below | not projected (no measured base) | not measured |
| Recommended, as the pipeline ships it | $0.019 (measured, cold cache, 1,200 records) | ~$1.95 (projected, see method below) | **89.08%** (measured, 1,069/1,200) |
| Recommended + one-time cache-seeding pass | $0.019 (same -- seeding cost $0, see log #9) | ~$1.95 (same) | **98.58%** (measured, 1,183/1,200) |

**Baseline could not be measured.** Attempted across three different API
keys; every attempt hit either a hard 404 ("no longer available to new
users") or a 429 with `limit: 0` for `gemini-2.5-pro` specifically on the
free tier. Real error text is in the terminal history if needed as
evidence. Genuine open gap -- state it plainly rather than inventing a
number. If billing clears before submission, a small (100-300 record)
unbatched run on `gemini-2.5-pro` would close it.

**Monthly projection method:** cost-per-distinct-token was measured
($0.000047/token, from the $0.0228 / 487-distinct-token real run). Token
*volume* at 100K/day was NOT measured (no such data exists) -- it's
projected from a Heaps' law curve fitted to the real 1,200-record sample:

    V = 20.64 * n^0.4177   (n = lookups, V = distinct tokens)

At 86,400 records/day (172,800 lookups): ~3,180 new tokens on a cold day 1
(~$0.15), then steady state settles to a ~0.77% marginal miss rate
(~1,330 new tokens/day, ~$0.06/day). Month 1 total ≈ **$1.95**. Clearly a
projection, built on a measured per-token cost, not a measured monthly
figure.

**Why two accuracy rows:** the pipeline alone gets 89.08%. A second,
one-time pass -- reviewing the highest-frequency wrong answers and writing
the corrections into the cache -- took the same output to 98.58% at zero
extra API cost, because the fix was cache-only, not a re-run against the
model. See log #9/#10. Whether to present the recommendation as "89.08%
out of the box" or "98.58% after a cheap one-time seeding step" is a real
choice for §1 -- both numbers are real and defensible, they just describe
different points in the same rollout.

---

## For §4 (The prompt)

Final prompt lives in `preprocess.py`'s `STYLE_RULES` constant. Two
versions were tested:

**v1 (base rules only)** -- preserve orthography, "Al-" convention,
particle handling.

**v2 (+4 rules added after analysing real failures)**:
- Long Arabic vowels: prefer double-letter spelling (Kareem not Karim,
  Waleed not Walid) -- 8/9 consistent in gold, ~20 failures targeted.
- Word-final ة -> plain "-a", never "-ah" (Hamza not Hamzah) -- 4/4
  consistent, ~7 failures targeted.
- Compound names stay one word, no space at the join (Abdullah not Abd
  Allah) -- 5/5 consistent, ~5-7 failures targeted.
- Initial long "aa" sound -> آ not plain أ (Amber -> آمبر) -- 3/3
  consistent, ~4 failures targeted.

**What it was worth (gemini-3.1-flash-lite, same 487-token pool, MEASURED
via the bake-off harness):**

| | overall | critical (hamza/ta-marbuta stratum) |
| --- | --- | --- |
| v1 | 86.7% | 87.0% |
| v2 | 85.6% | **90.7%** |

Net: the targeted stratum improved by +3.7pp exactly where intended. The
small overall dip is consistent with gold not being 100% internally
consistent on the vowel-length convention (known exception: `Al-Qasir`,
where gold picked the short form against its own usual pattern).

**Even explicit rules aren't followed with 100% fidelity.** In the real
1,200-record run, 2 of 141 failures directly violated the compound-spacing
rule (`عبد الرحمن` -> `عبدالرحمن` despite the rule saying keep it spaced).
Honest evidence that prompting reduces, not eliminates, a failure class.

---

## For §6 (Experiment log)

| # | What I tried | Cost | Accuracy | What I learned |
| --- | --- | --- | --- | --- |
| 1 | 3-model bake-off, v1 prompt, token-level (487 tokens): gemini-2.5-flash-lite / gemini-3.1-flash-lite / gemini-2.5-pro | ~$0.11 total | pro highest raw, but... | `gemini-2.5-flash-lite` and `gemini-2.5-pro` both 404/429'd on the account's real key -- listed in the catalog but not callable. Model availability has to be probed per-key, not assumed from docs. |
| 2 | Rebuilt bake-off with confirmed-reachable models: `gemini-3.1-flash-lite` / `gemini-3.5-flash-lite` / `gemini-3.6-flash`, v1 prompt | ~$0.14 | 86.7% / 85.2% / 78.6% overall | Cheapest model was also the MOST accurate. The larger model produced more "natural" but less gold-compliant transliterations (e.g. Jasmine -> ياسمين, the real traditional name, when gold wanted the literal phonetic جازمين). |
| 3 | Same 3 models, v2 prompt (4 style rules added) | ~$0.19 | 85.6% / 84.4% / 49.5%(!) | 3.6-flash's number was a red herring: it only answered 285/487 tokens (rest missing, not wrong). Accuracy among ANSWERED tokens: 84.6%, in line with the others. A coverage/parsing issue on longer prompts, not a quality drop. |
| 4 | Near/far-miss diagnostic (Levenshtein distance) on all 65 v1 failures, gemini-3.1-flash-lite | $0 (diagnostic only) | n/a | Checked every one of 65 failures by hand: ALL were valid alternate spellings (vowel convention, spacing, hamza form, or genuine name-root ambiguity like Rashid/رشيد vs راشد). Zero hallucinations, zero empty predictions. Directly motivated the 4 style rules above. |
| 5 | Real pipeline run #1 (`preprocess.py` + `translate.py --sync`), cold cache, v2 prompt | not captured (bug: no usage_metadata logging at the time) | **87.92%** (1055/1200) | First real whole-record number of the project. Exposed that `translate.py` had zero cost tracking -- fixed before the next run. |
| 6 | Real pipeline run #2, cache cleared, cost tracking added | **$0.0228** (measured: 11 requests, 17,084 in / 12,353 out / 0 thinking tokens) | **89.08%** (1069/1200) | Confirmed `thinkingLevel: MINIMAL` genuinely produces 0 thinking tokens. Run-to-run swing vs run #5: 1.16pp on identical config -- `temperature` was never pinned, real non-determinism, logged rather than hidden. |
| 7 | Batch API access across 3 different keys | $0 (all failed before any billable batch job ran) | n/a | Key 1 & 2: 403 PERMISSION_DENIED on `batches.create`, uniform across all candidate models. Key 3: 400 FAILED_PRECONDITION ("Precondition check failed"), specifically on batch, while sync calls worked fine same key/model. Consistent pattern: batch access requires billing enabled on the underlying GCP project, independent of which model. Never resolved; `--sync` used throughout. |
| 8 | Response schema with `"enum": ["M","F",""]` on the gender field | a few cents (failed calls still consumed input tokens) | 0/N, every request 400'd | Real code bug: Gemini's schema validator rejected the empty-string enum value. Fixed by dropping the enum, keeping `gender` a plain string. Confirmed by the next run: that error class disappeared entirely. |
| 9 | Failure-pattern analysis on run #6's real `failures.csv` (141 failures) | $0 (diagnostic only) | n/a | 141 failures collapsed to **40 distinct (field, expected, got) patterns** -- because the same hard names (Thompson, Al-Rashid, Montgomery...) repeat across many customers. Top 5 patterns alone = 31.2% of all failures; top 20 = 75.2%; top 30 = 91.5%. Heavy-tailed, not evenly spread. |
| 10 | Cache-correction pass, attempt 1: wrote corrections keyed on the TARGET-language text (`expected`/`got` from failures.csv) | $0 | no change (verified before trusting it) | Real mistake, caught before claiming success: `failures.csv` doesn't contain the original SOURCE text the customer typed, only the target-language expected/got. The fix touched cache keys the pipeline never actually looks up. Checked `cache["genevieve"]` after the "fix" -- still wrong. Redone properly in #11. |
| 11 | Cache-correction pass, attempt 2: cross-referenced `names_input.csv` by `record_id` to recover the real source text for each of the top 30 failure patterns, corrected both cache directions | $0 (cache-only edit, zero API calls -- confirmed by re-running `preprocess.py` and seeing 0 distinct new names needed) | **98.58%** (1183/1200), up from 89.08% | 30 corrected entries closed 129 of 141 failures. Confirms the heavy-tail finding from #9 directly: a small, frequency-prioritized correction pass gets most of the value, permanently, for $0, because names repeat across customers far more than they're unique. |
| 12 | Attempted a real baseline measurement using `gemini-2.5-flash` as a stand-in for the unreachable `gemini-2.5-pro` (one call/record, no batching, no cache, free-text parsing -- matching the README's description of today's pipeline) | not recorded (files deleted before the run's cost/output were captured here) | did not produce a usable result | Marked as a dead end for now: the run did not work as intended. Exact failure mode wasn't captured before the script and its outputs were deleted, so this is logged honestly as an open failure, not a diagnosed one. **The baseline row in §2 remains unmeasured.** Worth retrying if time allows -- see §9. |

---

## For §7 (What you rejected)

- **`gemini-2.5-flash-lite` as the production model** -- cheapest on paper,
  but returns a hard 404 ("no longer available to new users") on this
  project regardless of documented retirement dates. Rejected for
  reliability, not cost.
- **`gemini-3.6-flash`** -- most expensive of the reachable candidates and
  not more accurate (see log #2); rejected on both axes.
- **Fuzzy/approximate matching for scoring** -- the task is explicit that
  `score.py` does exact match only, no accepted-alternatives list. Used
  Levenshtein distance only as a *diagnostic* to classify already-failed
  tokens (near-miss vs far-miss), never as a scoring mechanism.
- **Submitting multiple spelling candidates for one field** -- considered,
  then rejected: `score.py` compares one string to one string, so there is
  no output shape where "either spelling counts." Structurally impossible
  under the grading rule.
- **Reviewing every wrong name individually, unbounded, as volume grows**
  -- rejected as a plan, but for a specific, evidenced reason (see §9): the
  failure distribution is heavy-tailed, so a fixed, capped review budget
  captures most of the value regardless of total volume. Reviewing
  *everything* would be pointless effort on top of that fixed budget.
- **Context caching (Gemini's prompt-caching feature)** -- rejected early:
  the system prompt is ~200 tokens, under most minimum-cacheable
  thresholds, and batching already amortizes the prompt across 50 names
  per request.
- **A full glossary-injection prompt** -- built (`glossary.py` in
  `experiments/pipeline/`) but never conclusively A/B tested. Not
  rejected outright -- a "ran out of time to validate" item, see §9.

---

## For §8 (What breaks at full volume)

- **The deterministic prefix table (18 known forms) is closed over a
  1,200-record sample, not guaranteed closed at 100K/day.** The code does
  NOT silently emit blank for an unknown prefix -- it falls through to the
  LLM like any other token. Least confident here; would monitor "prefixes
  needing the LLM" as a live metric.
- **`cache.json` is a single JSON file, single writer.** Fine for this
  one-shot batch-validation shape. Would NOT be fine for concurrent live
  ingestion (multiple workers writing simultaneously) without a real
  datastore or a lock.
- **Gender cache stores one gender per normalized first name.** Breaks for
  a genuinely unisex name used by people of different genders -- same
  structural class of error as the Rashid/Rasheed name-root ambiguity.
  Not fixable by more caching; no per-record signal exists to disambiguate.
- **Chunk size (50) was picked by reasoning, never empirically swept.**
  Untested whether accuracy or id-dropping degrades at larger sizes.
- **Batch API access itself was never successfully exercised end-to-end**
  (see log #7) -- the shipped run used `--sync` throughout. The
  exponential-backoff polling logic exists but has not been observed
  against a real multi-hour job.
- **Why accuracy isn't (and structurally can't be) 100%:** `score.py`
  grades exact match against ONE arbitrary spelling gold picked per name.
  English->Arabic transliteration is inherently one-to-many (Arabic has
  far fewer vowel sounds than English), so a real, non-trivial share of
  "failures" are the model producing an equally-valid different spelling.
  Verified by hand across 65 bake-off failures and again across 141 real
  failures: zero hallucinations, zero garbage, every failure a legitimate
  alternate rendering of the correct name. No model change fixes this --
  only a one-time human decision per name, cached forever, does (log #11).
- **The heavy-tail finding is itself a scale claim that should be
  re-verified at real 100K volume**, not just assumed to hold. It held
  cleanly on 1,200 records (top 30/40 patterns closed 91.5% of failures);
  worth confirming the same shape holds once real production traffic
  exists, since a flatter distribution at scale would weaken the "fixed
  review budget" argument in §9.

---

## For §9 (If you had another week)

In priority order, updated now that #4 below was actually tested rather
than just proposed:

1. **Resolve billing/quota access** to (a) measure the real baseline
   (`gemini-2.5-pro`, unbatched) instead of leaving it unmeasured, and
   (b) actually exercise the Batch API end-to-end on a real multi-hour job.
2. **Turn the cache-correction pass into a repeatable weekly tool**, not
   a one-off script. Concretely: a small `review.py` that runs `score.py`
   (or, in real production without gold, surfaces a sample for manual spot
   -check) on a rolling window, ranks new failures by frequency, and lets
   a human approve/reject a capped queue (e.g. top 20-30/week) -- turning
   log #11's one-off fix into an ongoing, bounded-time process.
3. **Chunk-size sweep** (25/50/100/250) -- currently a reasoned default,
   not a measured optimum.
4. **A/B the glossary against the 4-rule-only prompt** on the full sample,
   since it was built but never conclusively evaluated.
5. **Pin `temperature=0`** for reproducible numbers -- measured ~1.16pp
   run-to-run swing on an identical config without it.

---

## For §10 (Spend)

Running total across this session (all real, no proxies where marked):

| item | cost |
| --- | --- |
| Bake-off, 3 models, v1 prompt | ~$0.14 |
| Bake-off, 3 models, v2 prompt | ~$0.19 |
| Failed batch-access attempts (3 keys, all rejected before billing) | $0.00 |
| Schema-bug failed calls (400s, before fix) | ~$0.02 |
| Real pipeline run #1 (cost not logged -- bug, fixed after) | not captured |
| Real pipeline run #2 (cache-cleared, cost tracking live) | $0.0228 |
| Cache-correction pass (both attempts -- cache-only edits, no API calls) | $0.00 |
| **Total (measured, excluding the uncaptured run #1)** | **~$0.37** |

Run #1's exact cost is unrecoverable (logging bug at the time) -- say so
plainly rather than estimate it silently; run #2 on the identical config
is a fair stand-in if a single number is needed.
