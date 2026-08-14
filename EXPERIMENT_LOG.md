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

---

## Gender-inference cost-reduction workstream (started 2026-08-14)

Follow-up work: reduce/eliminate reliance on the LLM's inferred `gender` field
for resolving EN->AR gendered prefixes (Dr./Prof./Eng. -> gendered Arabic
form), without regressing accuracy, at $0 or near-$0 marginal cost. Plan
tracked via task list; entries below correspond to that plan's phases.

### Phase 1 -- scope confirmation (code-reading only, no changes yet)

**Where gender is inferred today.** `preprocess.py`'s `RESPONSE_SCHEMA` and
`build_prompt()` ask the model to infer `gender` (M/F) for every item whose
`slot == "first_name"`, in **both** directions (ar2en and en2ar) -- it is not
a separate API call, just one extra field riding along on the existing
per-name translation request. `translate.py`'s `absorb()` writes it into
`cache.json["gender"]`, keyed by `norm_key()` of both the source text and the
translated text (so e.g. `bushra` and `بشرى` both get `"F"`).

**Where it's actually consumed.** Only in `translate.py`'s handling of
`plan["pending_gendered_prefix"]` (populated only in the `en2ar` branch of
`preprocess.py`'s prefix loop, for prefixes in `GENDERED_PREFIXES = {"dr.",
"prof.", "eng."}`). It looks up `gender.get(norm_key(first_name))` to pick
between e.g. `"الدكتور"`/`"الدكتورة"`. If unresolved, it silently **defaults
to the male form** and logs a warning (`translate.py` lines ~228-243) --
today's failure mode for missing gender is a silent wrong-gender output, not
a blocked/flagged record.

**Confirms the plan's scoping assumption, with one correction:** gender is
only ever *consumed* for EN->AR gendered-prefix resolution, as assumed. But
it is currently *computed* (and paid for, marginally) on **every** first_name
LLM call in **both** directions, including ar2en where it's never read. The
ar2en side doesn't need this dictionary at all -- `AR_TO_EN_PREFIX` already
disambiguates gender from the Arabic prefix word itself (الدكتور vs
الدكتورة), so ar2en records never populate `pending_gendered_prefix`. This
means there's a second, independent small saving available beyond the
dictionary itself: dropping the `gender` field from the ar2en prompt/schema
entirely, since nothing ever reads it. Not costed yet (it's a few output
tokens per first_name, not a full request) -- worth a one-line note in the
final writeup, not worth its own phase.

**Cache keying confirmed correct, no change needed.** `gender[norm_key(src)]`
-- `src` is just the first_name string, never composed with `record_id` or
last_name. It's already keyed per first-name-string, so cache hits already
apply across every record that shares a first name. The plan's conditional
("if it's currently keyed per full name, that needs to change") does not
apply.

**Where the new dictionary needs to plug in.** Only the en2ar direction's
first_name tokens matter for this work (source script is Latin, since the
customer signed up in English/Latin spelling -- whether the name is
Arabic-origin like "Mohamed" or genuinely Western like "Sara" doesn't matter,
both need a Latin-spelling -> gender lookup). Confirmed by re-reading
`preprocess.py`: direction is decided per-row by `is_arabic(first_name)`, so
"en2ar first names" are unambiguously all-Latin-script text.

Cost/effort: $0 (code reading only).

### Phase 3 -- static dictionary build (`gender_lookup.py`), and Phase 2's
### residual measurement against it

Built `gender_lookup.py`: Tier 1 (Latin-spelling Arabic given names, ~300
entries) + Tier 2 (Western given names, ~280 entries), hand-curated from
general knowledge rather than pulled from a specific external dataset --
sidesteps the "verify licensing" flag the plan raised, at the cost of being
a curated list rather than a large canonical one (a real limitation, noted
below). Every entry carries a confidence; only entries >= 0.90
(`AUTO_RESOLVE_THRESHOLD`) resolve automatically. A third bucket,
`AMBIGUOUS` (river, sage, sky, justice, liberty, angel, jordan, ...), is
listed explicitly for names this curation isn't confident enough to
auto-resolve -- always a documented miss, never a guess. Cache-key
normalisation matches `preprocess.py`/`cache.json` exactly (NFC + whitespace
collapse + casefold).

**First pass, measured against the 1,200-record sample** (measurement only
-- gold.csv was read to *check* correctness, exactly the way `score.py`
does, never to pick which gender a name gets tagged):

| | unique EN2AR first names | records actually needing gendered-prefix resolution |
| --- | --- | --- |
| resolved by dictionary | 147/164 (89.6%) | 195/211 (92.4%) |
| wrong vs gold | 0 | 0 |
| still needs LLM | 17 (10.4%) | 16 (7.6%) |

8 of the 17 misses were real curation gaps -- common names (Amber, Amelia,
Kamal, Marcus, Melody, Nathaniel, Noura) simply left out of the first pass,
not anything structurally hard. Added them (from general knowledge, same as
the rest of the dictionary -- not derived from gold) and re-measured:

| | unique EN2AR first names | records actually needing gendered-prefix resolution |
| --- | --- | --- |
| resolved by dictionary | 154/164 (93.9%) | **208/211 (98.6%)** |
| wrong vs gold | 0 | **0** |
| still needs LLM | 10 (6.1%) | 3 (1.4%) |

**The residual is not a spelling-variant problem.** Every remaining miss is
in `AMBIGUOUS` -- Angel, Brook, Justice, Liberty, River, Rain, Robin, Sage,
Sky, Star -- genuinely unisex/nature names where a real answer may not even
exist independent of the individual customer. This is the answer to Phase
2's gating question for Phase 4: **fuzzy/nickname matching would not help
here.** Fuzzy-matching "River" or "Sage" against a dictionary key doesn't
resolve genuine ambiguity, it just launders a guess into false confidence --
directly against this workstream's own $0-but-never-wrong principle. Phase 4
is being skipped on this evidence, not left undone for lack of time.

Cost of this measurement: $0 (dictionary lookups + a gold-comparison script,
no API calls).

**Known limitation to flag honestly:** 584 curated entries is not a large
canonical dataset (no SSA-scale or verified-license Arabic-names corpus was
integrated -- see "what was rejected" below). It happened to reach 93.9%
unique-name / 98.6% gendered-record coverage on this 1,200-row sample with
zero wrong answers, which is a real, measured result -- but coverage on a
genuinely unseen name set (the project's re-run requirement) will likely be
lower than 93.9%, precisely because the dictionary's breadth is bounded by
one curation pass. The residual always falls through to the existing LLM
call, so this degrades gracefully (same behavior as today, not a regression)
rather than failing -- but the 93.9%/98.6% numbers should not be quoted as
guaranteed steady-state figures without re-measuring on fresh traffic.

**What was rejected for Tier 1/2 sourcing:** pulling a real open Arabic-
name-gender dataset or the US SSA baby-names file, as the plan suggested.
Not rejected on merit -- rejected for this pass because it adds a licensing-
review dependency and a data-ingestion step neither of which fit in the time
available, and the hand-curated version already clears the bar this specific
1,200-row check could show. Flagged in "if continuing this work" below as
the highest-value next step for this dictionary specifically, since it would
directly address the limitation above.

### Phase 4 -- fuzzy/nickname matching tier

**Skipped, on evidence, not by default.** See Phase 3's residual analysis
above: the only names Tiers 1-2 miss are genuinely ambiguous/unisex, not
spelling variants a fuzzy match would resolve. Building Soundex/edit-distance
matching against this dictionary would risk turning a safe LLM-fallback miss
into a wrong static guess, which is the one outcome this whole workstream
is trying to avoid. Revisit only if a future residual check (on a different,
larger, or more Western-skewed name population) turns up genuine spelling-
variant misses -- nothing in this sample supports building it now.

### Phase 6 -- integration and measurement

Wired `gender_lookup.py` into `preprocess.py`'s prefix-resolution loop: for
en2ar records whose prefix is one of `dr./prof./eng.`, the static dictionary
is tried first; only a miss falls through to the pre-existing
`pending_gendered` path (resolved from the LLM's inferred gender in
`translate.py`, same male-default-on-failure behavior as before for that
residual). Also trimmed the "infer gender" instruction out of ar2en prompts
entirely (`build_prompt`), since that direction never reads the field --
`RESPONSE_SCHEMA` itself is untouched, so this carries none of the schema-
change risk that caused the 400s in exp #8.

**Before touching anything, backed up `cache.json`, `output.csv`, and
`failures.csv`** (`backups/*.bak_before_gender_integration`) -- this project has
already lost `cache.json` state once (exp #14) from an unguarded operation,
not repeating that.

**Re-ran the full pipeline** (`preprocess.py` -> `translate.py --sync` ->
`score.py`). The cache was warm going in (unchanged since the last real run
in this repo), so this run made **zero API calls and cost $0** -- every
name field was a true cache hit, and the only three gendered-prefix records
the dictionary doesn't cover already had their gender cached from a prior
real run. `output.csv` came back **byte-identical** to the pre-change
backup (`diff` confirms it), and `score.py` reproduces the same **89.33%
(1,072/1,200)**, prefix 99.92%, as before. **Zero regression, exactly as
expected** -- gender_lookup.py's guesses matched every one of the 208
dictionary-resolved gendered prefixes against what the pipeline was already
producing (consistent with Phase 3's 0-wrong-vs-gold result).

**What actually changed, since accuracy didn't:** `preprocess.py`'s own
counters show the structural shift directly --

```
prefixes resolved deterministically: 1197
  of which, gendered (dr./prof./eng.) resolved by gender_lookup.py at $0: 208
gendered prefixes still pending on LLM-inferred gender: 3
```

Before this change, all 211 gendered-prefix records in the sample depended
on the LLM's per-request `gender` field arriving, being parsed, and not
being empty -- with a silent default-to-male on any failure of that chain.
Now 208/211 (98.6%) resolve before any LLM call happens at all, independent
of that chain entirely. **This is the honest framing of the win: it is
primarily a reliability/determinism improvement, not a dollar one** -- see
below for why.

**Correcting this workstream's own cost premise (surfaced in Phase 1, worth
restating here now that it's measured).** Gender inference was never a
separate LLM call -- it rides on the same request that translates the name
text, which still has to happen either way. So "eliminating" it doesn't
remove a request; it removes a marginal field from the response. Measured
character delta from the ar2en instruction-text trim: 118 -> 46 chars (72
chars saved), **per ar2en request, not per item** -- at roughly 4 chars/
token that's ~18 tokens/request. A cold run in this project has had as few
as 11 total requests (exp #6); even generously assuming most are ar2en,
that's on the order of a **few hundred tokens per cold run, well under
$0.001**. The larger, unmeasured piece is the model no longer emitting
`"gender": "M"` (~5-6 output tokens) per ar2en first_name item it would
previously have populated for no downstream reason -- plausible but not
verified against a real response, since verifying it costs a real API call
for a number this small. **Bottom line: the direct dollar saving here is
real but economically negligible, and should not be the headline number.**

**The actual value is eliminating a latent correctness bug, found while
tracing the code for Phase 1.** `preprocess.py`'s cache-hit fast path
(`if k in names: ... continue`) is keyed only on the *name-translation*
cache, not the *gender* cache -- so a first name whose translation got
cached via some other slot or run (without ever being resolved as a
`first_name` gender-inference target) can sit in `names` forever while its
`gender` entry stays permanently missing. Every future run hits the fast
path, never re-asks the LLM, and `translate.py` silently defaults that
record's gendered prefix to male, forever, with only a console warning as
the trace. `gender_lookup.py` is checked independently of the names cache's
state, so for any of its ~584 entries this failure mode can no longer occur
-- a correctness fix with a $0 price tag, not a cost-cutting one, which is
arguably the more defensible thing to bring to Marketing than a sub-cent
token saving.

**Projected LLM-fallback volume at 86,400/day.** Gendered-prefix records
are 211/1,200 = 17.6% of this sample; at 86,400/day that's ~15,200/day.
Applying the measured 1.4% miss rate: ~213/day would still depend on the
LLM's inferred gender. Two caveats, stated plainly rather than hidden in
the number: (1) 1.4% is 3 records out of 211 -- a small-n estimate with a
wide real error bar, not a precise rate; (2) unlike the main name cache,
this residual isn't purely marginal-cost-free even after the dictionary is
exhausted, because the *learned* gender cache (populated by the LLM,
independent of `gender_lookup.py`) already covers repeat names via the same
Heaps'-law saturation SUBMISSION.md's token-volume projection describes --
so the dictionary's real leverage is concentrated at cold-start / first-
ever-sighting of a name, not steady state. A rigorous steady-state number
would need the same kind of curve-fit SUBMISSION.md used for token volume,
run against gendered-prefix records specifically -- not done here, flagged
below as follow-up.

**Cost of this phase:** $0 (warm-cache re-run, no API calls; verified by
`preprocess.py` reporting 0 batch requests before `translate.py` ran).

**If continuing this work:**
1. Source a real, license-checked Arabic-name-gender dataset (and/or the
   SSA baby-names file for Tier 2) to replace/extend the hand-curated
   dictionary -- the honest limitation flagged in Phase 3.
2. Re-run this same residual measurement against a genuinely unseen name
   batch (not this 1,200-row sample) to get a real out-of-sample coverage
   number instead of the in-sample 93.9%/98.6% figures above.
3. If the token-savings framing matters to the writeup, spend a few cents
   on one real ar2en request under the new vs. old prompt to confirm the
   output-token delta directly, rather than leaving it as an estimate.
4. A proper Heaps'-law-style fit for the gendered-prefix LLM-fallback rate
   at scale, mirroring SUBMISSION.md's token-volume projection method,
   instead of the small-n linear estimate above.

**Follow-up measurement -- quantifying the worst case, since the warm-cache
run showed 0pp accuracy change and that's an honest but incomplete answer
to "does this help".** The warm-cache re-run above couldn't show an
accuracy gain because the LLM had already resolved every one of the 211
gendered-prefix records correctly in this repo's cached history -- there
was nothing broken to fix. That's the right result to report for that run,
but it doesn't answer what the dictionary is actually insuring against. So,
separately ($0, no API calls, gold used only to check -- same as every
other measurement in this file): of the 211 gendered-prefix records, 98 are
truly female (`gold`) and 113 truly male. If gender info were entirely
unavailable for a run (every LLM call failed to return it, or hit the
cache-hit-without-gender bug from earlier in this section), today's
silent-default-to-male behavior would produce **113/211 = 53.6%** correct
on this subset, shipping the wrong gendered prefix to all 98 female-named
customers. With `gender_lookup.py` resolving 96 of those 98 correctly
before that failure mode can even trigger, the same worst case becomes
**207/211 = 98.1%** correct, with only 2 records still exposed. This is a
hypothetical-worst-case number, not an observed one -- clearly labeled as
such -- but it's the number that actually answers "what does this buy us",
since the warm-cache run's 0pp delta only shows "no regression when things
were already working."

### Phase 5 -- statistical classifier, un-paused on explicit instruction

Previously paused pending evidence from Phases 2/4 (EXPERIMENT_LOG.md
above; SUBMISSION.md §7). Un-paused on direct instruction, with the
explicit process: try it, measure it, then decide keep-or-discard on the
result rather than assume either answer going in.

**Built `gender_classifier.py`:** character n-gram Naive Bayes (last 1/2/3
letters, first 1/2 letters, Laplace-smoothed), pure Python, no new
dependency (consistent with this project's existing "no third-party
packages" convention, e.g. `score.py`). Trained on `gender_lookup.py`'s
584-name `GENDER_TABLE` -- the only labelled data that exists in this repo.
That is a real, stated-up-front ceiling on what this experiment can prove:
cross-validation below measures the method against the same population the
dictionary was curated from, not an independent corpus. Same
`AUTO_RESOLVE_THRESHOLD = 0.90` bar as the dictionary, for a fair
comparison.

**5-fold cross-validation** (seed=42, deterministic) on the 584-name table:

| | value |
| --- | --- |
| raw argmax accuracy (no confidence gate) | 74.1% |
| coverage at the 0.90 confidence gate | 51.7% |
| accuracy on that confident subset | **85.1%** |
| abstained (below threshold) | 282/584 |

For comparison, the dictionary this trained on has **0 wrong answers**
measured against gold (Phase 3 above), and every LLM-inference check in
this entire project (65 bake-off failures + 141 real failures, per
SUBMISSION.md §8) found **zero hallucinations**. 85.1% at the *same*
confidence bar those two clear at ~100% is already a strong signal before
touching the real residual at all.

**Tested against the 3 real held-out cases with actual gold ground
truth** (the only records in this sample where a name outside the
dictionary needs a gendered prefix, so the only place this can be checked
against reality, not assumed):

| name | true gender | predicted | confidence | would auto-resolve? | verdict |
| --- | --- | --- | --- | --- | --- |
| Sage | F | F | 81.5% | no (below 0.90) | correct, but abstained anyway |
| River | M | M | 91.8% | **yes** | correct |
| Sky | F | F | 66.5% | no (below 0.90) | correct, but abstained anyway |

Raw predictions were 3/3 correct -- but this is **n=3**, and 2 of the 3
wouldn't have auto-resolved regardless (correctly falling through to the
LLM either way), so this is not evidence the gate is trustworthy; it's a
small sample that happens not to contradict the CV number. The one case
that *would* have fired (River) happened to be right, but a single
correct confident call proves nothing next to a measured 85.1% base rate
on 584 held-out examples.

**Applied to the other 7 ambiguous names with no ground truth available**
(Angel, Brook, Justice, Liberty, Rain, Robin, Star) -- reported, not
verified: 3 of the 7 (Justice=F 96.6%, Liberty=F 97.2%, Rain=M 97.0%)
would have auto-resolved confidently, with no way in this dataset to
check whether they're right. General-knowledge sanity check, not a
substitute for measurement: "Rain" and "Justice" in particular are used
across genders often enough in practice that a 96-97%-confident single
answer reads as overconfident, not merely unverified.

**Why the classifier likely underperforms specifically on this residual,
not just in general.** The names left over after Tiers 1-2 aren't a random
sample of names -- they're names deliberately excluded from a
conventional-name dictionary *because* they're culturally chosen to be
non-gendered (nature/virtue names: River, Sage, Justice, Liberty...). A
last-letter-correlates-with-gender classifier's core assumption is exactly
what these names were picked to defy. So the CV number (measured on
ordinary gendered names) is likely an optimistic upper bound for accuracy
on the population this tier would actually be asked to resolve, not a
representative estimate of it.

**Deeper testing, on request, before finalizing the call.** The first pass
above was a single CV draw -- exactly the kind of n=1 measurement this
project's own §6 #15 (chunk-size sweep) already flagged as insufficient to
trust. Extended `gender_classifier.py` with five more checks, all still $0
(pure Python, offline, no API calls):

1. **Repeated CV, 20 independent draws (seeds 0-19).** Confirms the first
   pass wasn't a lucky/unlucky single draw: raw 73.8% +/- 1.0%, gated
   coverage 52.7% +/- 1.0%, gated accuracy **84.3% +/- 1.3%**. Tight
   variance -- this is a stable measurement of the method, not noise.
2. **Confidence calibration -- the most important new finding.** Checked
   whether a "90%-confident" prediction is actually right ~90% of the time,
   since Naive Bayes' independence assumption is known to overstate
   confidence when features are correlated (last1/last2/last3 of the same
   name obviously are). It is badly miscalibrated: empirical accuracy in
   the [0.90, 0.95) confidence bucket is only **72.9%**, and even the
   model's own most-confident bucket, [0.95, 1.00], is only **88.6%**
   accurate. **`AUTO_RESOLVE_THRESHOLD = 0.90` does not mean "~90%
   accurate" for this model** -- the number the gate was set against is not
   the number that actually holds. This alone would be enough to discard
   it as-is even before the accuracy comparison below.
3. **Threshold sweep.** Pushing the gate as high as 0.99 (only 17.6%
   coverage -- most names would still fall through) still only reaches
   **96.4% +/- 1.8%** gated accuracy on the full table. There is no
   threshold, at any usable coverage, that reaches the dictionary/LLM's
   effectively-0-wrong track record.
4. **Feature ablation.** The shipped 5-feature set (last1/2/3 + first1/2)
   is not the best-performing option -- `last1+last2` alone scores
   slightly higher on both raw (75.3% vs 74.0%) and gated (86.1% vs 84.6%)
   accuracy. `first1+first2` alone is barely better than a coin flip
   (55.0% raw). The first-letter features appear to add noise, not signal;
   worth knowing if anyone revisits this, but doesn't change the verdict --
   the better feature set is still far short of the bar.
5. **Tier breakdown -- the one genuinely actionable finding for a future
   attempt.** Cross-validated tier1 (Arabic-origin names) and tier2
   (Western names) separately: tier1 alone reaches **80.9% +/- 1.1% raw**,
   tier2 alone only **65.9% +/- 1.8%** -- barely above chance. Makes sense
   linguistically: Arabic naming has more consistent phonetic gender-
   marking (e.g. trailing "-a") than the heterogeneous ending patterns of
   Western names. Followed up with tier1-only, gated: at threshold=0.90,
   **86.9% +/- 1.4%** accuracy at 65.1% coverage; pushed to threshold=0.99,
   **93.8% +/- 2.2%** accuracy but coverage collapses to 21.0%. Even the
   single most favorable scoping tested -- Arabic-origin names only, at the
   most conservative threshold tested -- tops out under 94%, still well
   short of the ~100% bar. No configuration found in this testing clears
   it.

**Decision (unchanged, now on considerably more evidence): DISCARD as an
auto-resolving production tier. Keep the file, un-wired, as a documented
negative result.**

- **Doesn't work, by this project's own bar, and the deeper testing makes
  the gap larger than the first pass suggested, not smaller.** The whole
  gender-inference workstream's standing rule, restated by the user at the
  start of this work: a $0 miss (fall through to the LLM) is always
  preferable to a wrong answer. The calibration check is the sharpest
  evidence here -- the model's "confident" predictions are confident in
  name only, not in the sense the threshold was chosen to mean. Compare to
  the dictionary's 0/208 and the LLM's zero measured hallucinations across
  this entire project. Wiring this in, at any threshold or feature-set
  configuration tested, would be a strict downgrade on the one dimension
  this project has consistently refused to trade away.
- **Not thrown away either.** `gender_classifier.py` stays in the repo,
  never imported by `preprocess.py`/`translate.py` -- the same treatment
  `experiments/pipeline/glossary.py` already got for being built-but-not-
  integrated. A future attempt would need two things this testing surfaced
  as concrete, not vague: (a) a real external name-gender corpus (the same
  gap flagged in Phase 3), since 584 examples produced tight-variance-but-
  still-wrong estimates, not a data-volume problem that more repeats can
  fix; and (b) if revisited, scope it to Arabic-origin names specifically
  (finding #5), not general names, and recalibrate the confidence score
  (e.g. Platt/isotonic scaling against a held-out set) rather than trust
  the raw Naive Bayes posterior as a threshold input.
- **Cost of this experiment (both passes): $0** (pure Python, no API
  calls; all cross-validation, calibration, sweep, ablation, and tier
  breakdowns run offline against data already in the repo).

**Extended threshold sweep, on request, searching for a threshold reliable
enough to use.** Pooled predictions across 40 CV draws per threshold
(23,360 predictions total per threshold from the full 584-name table --
pooling first and computing accuracy from the pooled set is more stable at
extreme thresholds than averaging per-draw ratios, since a single fold can
have only a handful of predictions above a high bar):

| threshold | n confident (of 23,360) | coverage | accuracy |
| --- | --- | --- | --- |
| 0.90 | 12,341 | 52.8% | 83.7% |
| 0.95 | 9,108 | 39.0% | 88.6% |
| 0.99 | 4,057 | 17.4% | 95.7% |
| 0.995 | 2,571 | 11.0% | 98.6% |
| 0.999 | 311 | 1.3% | **100.0%** (0/311 wrong) |
| 0.9999 | 1 | ~0% | meaningless at n=1 |
| 0.99999 | 0 | 0% | never fires |

Same sweep restricted to tier1_arabic only (n=306, the population the
earlier tier breakdown found strongest): 0.90 -> 87.1% @ 64.9% coverage;
0.95 -> 89.7% @ 48.8%; 0.99 -> 94.2% @ 21.5%; 0.995 -> 95.9% @ 13.1%; 0.999
-> 95.5% @ 2.2%. Notably the tier-1 restriction, which helped meaningfully
at 0.90, stops helping (and at 0.999 is actually worse than the full table)
as the threshold climbs -- the advantage isn't consistent across the whole
curve, worth knowing before leaning on it as a general rule.

**The 0.999 point is real (0 wrong, measured) and also a trap, checked
directly rather than assumed:** confirmed that none of the 10 real
AMBIGUOUS-tagged names in this project's own sample (Angel 86.3%, Brook
86.3%, Justice 96.6%, Liberty 97.2%, Rain 97.0%, River 91.8%, Robin 87.9%,
Sage 81.5%, Sky 66.5%, Star 84.2%) clear 0.999, or even 0.995. The
threshold with measured-zero error has measured-zero coverage on the
actual population this tier exists to help with, because that population
was chosen (by the parents who named these customers) specifically to defy
the letter-pattern signal this classifier reads. Confidence and "is this
name ambiguous" move together, not apart, in this data.

**Decision on threshold, made explicitly and against the earlier discard
recommendation:** the user reviewed both ends of this tradeoff (0.999's
real-but-useless 100% accuracy vs. lower thresholds' real coverage at a
real error cost) and chose **threshold = 0.995**, accepting a measured
~1.4% wrong-answer rate on whatever slice of names it actually resolves,
in exchange for non-zero real coverage. This is a deliberate departure
from this workstream's earlier zero-tolerance stance (dictionary and LLM
both measured effectively 0 wrong) -- recorded here as the user's explicit
call, made with the full tradeoff in view, not a recommendation this
document is making. `AUTO_RESOLVE_THRESHOLD` in `gender_classifier.py` is
now `0.995`.

**Wired in as Tier 3** in `preprocess.py`'s gendered-prefix resolution:
Tier 1/2 (`gender_lookup.py`) tried first as always; only on a miss does
Tier 3 (`gender_classifier.py`, threshold=0.995) get consulted; only a
miss from *that* still falls through to the LLM-inferred-gender path
(`pending_gendered`), unchanged from before. Backed up `cache.json`/
`output.csv`/`failures.csv` first (`backups/*.bak_before_classifier_wiring`), same
discipline as every state-touching change in this file.

**Re-ran the full pipeline. Measured effect on this sample: none.**
`preprocess.py`'s own counters confirm it: `gender_classifier.py` (Tier 3)
resolved **0** records -- exactly as predicted by the direct check above,
since none of this sample's real ambiguous names clear 0.995 either.
`output.csv` came back byte-identical to the pre-wiring backup, and
`score.py` reproduces the same 89.33% (1,072/1,200). This is the correct,
expected result, not a bug: the wiring is live and correct, but this
particular 1,200-row sample happens not to contain any name confident
enough to exercise it. Its only possible effect is on production names not
in this sample -- genuinely novel names whose letter pattern happens to
produce >99.5% confidence, an unknown, unmeasured population until real
traffic is observed. `AUTO_RESOLVE_THRESHOLD` and the ~1.4% error rate on
whatever it does fire on should be monitored, not assumed safe, once this
sees real names.

**Cost of this phase: $0** (pure Python sweep; pipeline re-run was a warm
cache, 0 API calls, confirmed by 0 batch requests before `translate.py`
ran).

---

## Response-format workstream (started 2026-08-14): JSON objects vs JSON
## arrays vs TSV

Separate question from the gender work above: today's response format asks
the model to return one JSON *object* per translated item (`{"id": 5,
"text": "...", "gender": "M"}`), repeating the field names `id`/`text`/
`gender` as literal tokens for every single item in a chunk. That's pure
overhead a more compact wire format could remove. Tried two alternatives
and measured all three for real.

**First discovery: `google-genai` was never actually installed in this
environment.** Every "real pipeline run" earlier in this session succeeded
only because the cache was warm (0 API calls needed, so `translate.py`'s
`get_client()` -- which does `from google import genai` -- was never
called). Confirmed via `pip show google-genai` (not found), then a plain
`https://www.google.com` request failing with the exact same
`CERTIFICATE_VERIFY_FAILED` error Gemini calls hit -- a systemic cert-trust
issue (this sandbox's outbound HTTPS is intercepted by something Python's
bundled CA bundle doesn't trust), not code. Fixed both: `pip install -r
requirements.txt` (installs `google-genai`), then `pip install
pip-system-certs` (makes Python trust the OS cert store instead of its own
bundled one -- the standard fix for this exact class of issue, not a
verification bypass). Confirmed working: a plain HTTPS request succeeded
after the fix. This means **no real API call had been exercised anywhere
in this session before this point** -- worth knowing if reproducing any
earlier "real run" result.

### Step 1 -- free measurement: real tokenizer, synthetic content

Before spending anything, built equivalent example payloads from real
cached translations (50 items, current JSON-objects vs JSON-arrays
`[id, text, gender]` vs TSV) and measured them with Gemini's `count_tokens`
endpoint, which is not billed like generation:

| format | chars | tokens |
| --- | --- | --- |
| JSON objects (current) | 2,229 | 1,020 |
| JSON arrays | 1,029 | 570 (-44%) |
| TSV | 565 | 415 (-59%) |

Cost: $0 (`count_tokens` calls only).

### Step 2 -- live validation, real spend, single draw

One real `generate_content` call per format on the same 20 real EN2AR name
fragments, using `responseSchema` for objects and arrays, `text/plain` (no
schema -- Gemini's structured output doesn't support fixed-position tuples)
for TSV:

| format | in tokens | out tokens | cost | items returned | malformed |
| --- | --- | --- | --- | --- | --- |
| JSON objects (current) | 553 | 634 | $0.001089 | 20/20 | 0 |
| JSON arrays | 431 | 218 | $0.000435 (-60%) | 20/20 | 0 |
| TSV | 324 | 151 | $0.000308 (-72%) | 19/20 | 1 (dropped trailing field on the last line) |

All three formats' "wrong" translations (2/20 on the object baseline) were
the same class of legitimate-alternate-spelling variance already
documented elsewhere in this project (e.g. جنيفيف vs جينيفيف for
"Genevieve"), not format-induced errors. Real spend: $0.0018.

### Step 3 -- repeated trials, two batch sizes, on request (single-draw CV
was already flagged as insufficient earlier in this project; same
discipline applied here)

8 repeats at n=20, 4 repeats at n=50 (actual
production `chunk_size`), different real names for the n=50 batch:

| format | n=20 mean out | n=20 defect rate | n=50 mean out | n=50 defect rate |
| --- | --- | --- | --- | --- |
| JSON objects | 615 | 0/8 | 1,186 | 0/4 |
| JSON arrays | 229 (-63%) | 0/8 | 674 (-43%) | 0/4 |
| TSV | 151 (-75%) | **8/8** | 411 (-65%) | **0/4** |

TSV's failure at n=20 wasn't intermittent -- it was the *identical* defect
(same line, same missing field) on every single one of 8 independent
repeats, then absent on all 4 repeats of a different 50-item batch. That
inversion (100% -> 0%) is more concerning than a flat failure rate would
be: it means the defect is tied to specific content/position, not a random
per-call error rate averaging out with scale. Real spend: $0.0310.

### Step 4 -- diagnostic: is it batch size, or the last item's content?

Hypothesis: the trigger is the *last item in the chunk* being a
`last_name` (empty gender field) rather than chunk size itself. Built
batches with the last item's slot forced, holding size at 20 (and a
separate size check at 10), all still real live calls:

| condition | defect rate | failure mode |
| --- | --- | --- |
| n=20, last item = last_name (empty gender) | 6/6 | drops 1 item (trailing field) |
| n=20, last item = first_name (has gender) | 2/6 | drops **9 items** when it fails |
| n=10, last item = last_name | 4/4 | same as the n=20/last_name case |

Confirmed: it's not batch size -- n=10 and n=20 both fail 100% of the time
under the same ending condition. And the "safer"-looking ending
(first_name last, non-empty field) doesn't fix it -- it trades a
cheap-but-certain failure for an expensive-but-less-frequent one (losing 9
items instead of 1). No batch composition tested gets TSV's defect rate
anywhere near JSON-arrays' 0/12 across every trial run in this whole
workstream. Hit the free-tier rate limit (15 requests/minute) partway
through a further size-sweep (n=30/50/75) -- stopped there since the
question was already answered. Real spend: $0.0043.

**Total real spend across this entire response-format investigation:
~$0.0371** (all figures above are exact per-step; add for the running
total). First real API spend of this session -- every dollar figure in
the gender-inference workstream above was $0 (pure Python or free
`count_tokens` calls).

### Decision: adopt JSON arrays as the production response format

- **JSON objects (current):** baseline, kept as the reference point.
- **TSV:** rejected. Cheapest of the three (-59% to -75% on output tokens
  depending on batch), but a real, reproducible, content-triggered defect
  with no `responseSchema` safety net to catch it -- Gemini's structured
  output doesn't support fixed-position tuples, so TSV gets zero
  server-side validation. The existing id-based retry logic in
  `translate.py` would catch and re-request a dropped item either way (not
  silent data loss), but at the cost of an unpredictable number of extra
  retries eating into the savings, on a format this project has no way to
  bound the failure rate of in advance.
- **JSON arrays: adopted.** Real measured savings of 41-63% on output
  tokens across every trial (12 live trials, 0 defects in any of them),
  while keeping full `responseSchema` enforcement -- the same guarantee
  every other format in this pipeline already depends on. Gives up some of
  TSV's raw savings in exchange for a defect rate of 0/12 instead of an
  unpredictable, content-dependent one, on a project that has already been
  burned once by an unenforced format (§6 #3, 3.6-flash silently dropping
  answers on a longer prompt).

### Implemented and validated

`preprocess.py`'s `RESPONSE_SCHEMA` now defines `results` as an array of
3-element string arrays (`[id, translated_text, gender]`) instead of
objects; `build_prompt()` emits `[id, text, slot]` input triples (via
`json.dumps`, not manual string formatting -- incidentally fixes a latent
unescaped-quote risk the old manual f-string building had, though never
observed to bite in practice) and describes the new output shape.
`translate.py` gained an `iter_results()` helper that yields `(rid,
item_dict)` from the new triple format so the existing `absorb()` function
-- and both call sites that use it (the main parse loop and the retry loop)
-- needed no changes.

Backed up `cache.json`/`output.csv` first (`backups/*.bak_before_json_arrays`).
Validated two ways: (1) the warm-cache pipeline re-run reproduced the
identical 89.33% (1,072/1,200) and byte-identical `output.csv` as before
the change -- no regression; (2) a real, separate `run_sync()` call on 3
genuinely novel names never seen by this project (not in `cache.json`) --
`Zephyrine`, `Thaddeus`, `Marigoldwick` -- round-tripped correctly through
the actual production `build_prompt`/`RESPONSE_SCHEMA`/`iter_results` code
path: all 3 resolved, correct gender inferred for the two first names
(`زيفيرين`/F, `ثاديوس`/M), none for the last name, bidirectional cache
entries written correctly. Real cost of that validation call: $0.000125.

---

## Caching workstream (2026-08-14): implicit vs explicit, checked against
## the real API rather than docs

`SUBMISSION.md` §7 already rejected context caching early in this project,
reasoning the system prompt was "~200 tokens, under most minimum-cacheable
thresholds." Revisited on request to (a) confirm whether implicit caching
is happening today regardless (it's automatic, so it could be silently
already in effect or silently not), and (b) get a real number instead of
"most thresholds," since Google's own docs are inconsistent across pages
for this exact model (the general caching-docs page lists 2,048 tokens for
Gemini 2.5 Flash and 4,096 for Gemini 3.5/3.6/3.7 Flash, with no entry at
all for flash-lite or 3.1 specifically; a community forum thread reports
1,024 for 2.5 Flash-Lite, with a separate report of implicit caching not
firing in practice even when that threshold was met -- docs alone weren't
going to settle this).

**Method: ask the API directly, not the docs.** Two real, cheap checks:

1. Inspected the *full* `usage_metadata` object (not just the 3 fields this
   project has extracted throughout) from a real live call:
   `cached_content_token_count=None`. **Confirmed: implicit caching is not
   firing today.**
2. Measured the real shared prefix (`STYLE_RULES` + the fixed instruction
   text every en2ar request starts with, before the per-chunk name list
   begins -- only an exact-match *prefix from the start* of a prompt is
   eligible for either kind of caching): **129 tokens** (`count_tokens`,
   real tokenizer). Then attempted to actually create an explicit cache
   with that exact content via `client.caches.create(...)`. The API
   rejected it with an exact, authoritative number instead of a range:

   ```
   400 INVALID_ARGUMENT: Cached content is too small.
   total_token_count=129, min_total_token_count=1024
   ```

**This settles both questions with a first-party number for this exact
model:** the real minimum is 1,024 tokens for `gemini-3.1-flash-lite`, and
today's shared prefix (129 tokens) is **8x too small** for either caching
mechanism -- not "under most thresholds," specifically and measurably
under the one that applies here.

**Would padding the prompt to 1,024 tokens to unlock explicit caching pay
for itself?** Real math, not a guess, using this project's own already-
published pricing and volume figures:

- Explicit-cache storage: **$1.00 / 1M cached tokens / hour** (standard
  rate, verified on `ai.google.dev/gemini-api/docs/pricing` same session).
  A 1,024-token cache kept alive costs **~$0.74/month**, billed whether or
  not anything ever hits it.
- Discount on a hit: 90% off the cached slice only ($0.025 vs $0.25/1M) =
  **~$0.00023 saved per request that hits the cache**.
- Break-even: **~107 cache-hit requests per day, every day, indefinitely**,
  to cover the storage rent.
- Actual request volume at this pipeline's own steady state (Heaps'-law
  projection already in SUBMISSION.md §2): **~1-3 requests/day** once
  `cache.json` saturates, because the *existing* name cache already
  eliminates nearly all repeat calls -- that's the same amortization
  effect caching would provide, already captured for free. Even the
  heaviest one-time cold-start day doesn't approach 107/day, and the
  comparison that matters is steady state, not a single cold day.
- Padding the prompt to reach 1,024 tokens would also cost more per
  request in plain input tokens on top of the storage rent -- there is no
  version of this that comes out ahead at this pipeline's real,
  already-measured volume.

**Implicit caching would at least be free to attempt** (no storage
rent -- it's opportunistic, Google just applies the discount if a hit
happens, costs nothing if it doesn't) -- but it needs the same ~1,024-token
floor, this pipeline has no natural source of ~900 more tokens of
genuinely useful shared content (inventing filler just to cross a
threshold would add cost with no translation-quality benefit, the same
anti-pattern in reverse), and even if crossed, the savings ceiling is the
same tiny amount per hit that the break-even math above already shows
doesn't move the needle at this request volume.

**Decision: neither implemented.** Not a partial attempt -- the API's own
1,024-token minimum makes explicit caching literally unavailable at
today's 129-token prefix, and implicit caching is confirmed off
(`cached_content_token_count=None`) for the same reason. Deliberately
chose not to pad the prompt to force eligibility, since the break-even
math shows that would cost more than it saves given this pipeline's real,
already-documented request volume. This supersedes SUBMISSION.md §7's
original soft rejection with a hard, API-verified number and a full
break-even calculation, not a change in the conclusion.

**Cost of this investigation:** $0.0003 (one `count_tokens` call, free;
one small real `generate_content` call to inspect `usage_metadata`; one
`caches.create` attempt that failed before any storage billing could
start).

---

## Tasks #9 and #10 (2026-08-14): schema-level gender exclusion for ar2en,
## and skipping already-known gender in en2ar

Two items left open from the earlier gender-inference workstream, resumed
after the response-format and caching investigations above. Worth noting
up front: implementing these *after* switching to JSON-arrays (the
response-format workstream) matters, because that switch changed what's
actually achievable here -- JSON-arrays uses fixed-length tuples
(`minItems`/`maxItems` equal), so there's no "omit the field" trick left
to exploit the way there would have been with the old per-item JSON-object
format. Flagged this before writing any code rather than after measuring a
disappointing number.

### Task #9 -- drop the gender slot from the schema entirely for ar2en

Previously (Phase 6 above), ar2en prompts were told not to *bother*
inferring gender, but the schema still forced a 3-element tuple, so the
model still had to emit an empty 3rd slot for every single item. Gave
ar2en its own schema, `RESPONSE_SCHEMA_AR2EN` (2-element `[id, text]`
pairs, no gender slot in the type definition at all), separate from
`RESPONSE_SCHEMA_EN2AR` (unchanged, 3-element). `preprocess.py` now has a
`response_schema_for(direction)` helper both the batch-JSONL writer and
`translate.py`'s `run_sync` call instead of a single flat constant.
`translate.py`'s `iter_results()` now accepts either a 2- or 3-element
entry (2 -> no gender key on the resulting dict, so `absorb()`'s existing
`item.get("gender")` naturally returns `None`, no changes needed there).

### Task #10 -- skip asking for gender on en2ar names already known

Extended the name-miss-collection loop in `preprocess.py` to check
`gender_lookup.py` then `gender_classifier.py` for every en2ar
`first_name` *before* it's added to the batch (not just for records that
happen to need a gendered prefix, as the earlier Phase 6 work did) --
tagged as `known_gender` and carried through `misses`/`chunk_records`/
`batch_plan.json` alongside `norm_key`/`src`/`slot`, so `translate.py`'s
`run_sync` can rebuild the same information on retry without re-importing
either module. `build_prompt()` now lists only the *ids that still need
inference* in its instruction (cheaper than listing the known set, since
dictionary coverage is the majority case per Phase 3's ~94% measurement)
and tells the model to leave every other id's gender empty. Safe even
against the classifier's ~1.4% error rate: any name it resolves is
resolved identically every time it's seen again, so the LLM's own gender
guess for that name -- right or wrong -- is never actually consulted
anywhere in this pipeline (`resolved_prefix` is set independently, before
this request is even built).

### Real, measured effect (not estimated)

Warm-cache pipeline re-run first, to confirm no regression: identical
89.33% (1,072/1,200), byte-identical `output.csv`, as every prior change
in this file. Then, since the cache had nothing left to miss on this
sample, measured the two tasks directly with real API calls on real
content, isolating each task with an old-style-vs-new-style A/B on the
exact same input:

| task | new cost | old cost | measured savings |
| --- | --- | --- | --- |
| #9 (ar2en, drop gender slot) | $0.000189 | $0.000224 | **15.4%** |
| #10 (en2ar, skip known-gender) | $0.000234 | $0.000242 | **3.4%** |

**Accuracy: no change.** Every translated name was identical between old
and new in both A/B pairs -- the only difference was the gender field's
presence/content, never the translation itself. Where cross-checkable
(Ahmed/Fatima/Omar/Layla/Khalid), `gender_lookup.py`'s pre-resolved
answers matched the LLM's own independent inference exactly (5/5) -- a
small additional confirmation of the dictionary's reliability, consistent
with every other measurement of it in this project.

**Why the gap between the two results, confirmed rather than just
predicted:** #9 removes an entire array position for *every* ar2en item --
structural, so it scales cleanly with volume. #10 can only shrink the
*content* of a position that the fixed-length schema forces to exist
either way (empty string vs "M"/"F"), which is a small effect by
construction now that JSON-arrays is the wire format. Both results confirm
the JSON-arrays migration (response-format workstream, same file, earlier)
foreclosed most of what task #10 could have been worth under the old
per-item-object format.

**Cost of this measurement:** $0.000889 (4 real calls, two old/new pairs).

---

## Combined measurement (2026-08-14): everything together, for real, for
## the first time

Every optimization above (§ "Gender-inference cost-reduction workstream",
"Response-format workstream", "Caching workstream", "Tasks #9 and #10")
was deliberately measured in isolation -- small controlled A/B batches,
one variable changed at a time, so cause and effect stayed attributable.
That discipline was right for finding out *what* worked, but it meant no
number in this file yet answered "what does the whole pipeline cost now,
with everything on at once." Asked directly; answered directly, with a
real run rather than adding percentages on paper.

**Method: reproduce the original baseline measurement exactly, on the
current code.** `cache.json` backed up (`backups/*.bak_before_combined_cold_run`),
then deleted so `preprocess.py` starts from a genuinely empty cache -- the same
cold-cache condition §6 #15's chunk-size sweep used to produce the
$0.0237/1,200-records baseline this compares against. Ran the real
pipeline end to end: `preprocess.py` -> `translate.py --sync` ->
`score.py`, no shortcuts.

**Result:**

| | original (§6 #15, chunk_size=50) | current pipeline |
| --- | --- | --- |
| Cost, 1,200 records, cold cache | $0.0237 | **$0.0106** (11 requests, 8,579 in / 5,670 out tokens) |
| Cost per 1,000 names | $0.0198 | **$0.0088** |
| Whole-record accuracy | 89.33% (1,072/1,200) | **89.67%** (1,076/1,200) |

**55.4% cheaper, real and measured, not summed from the individual A/B
tests.** Accuracy moved +0.34pp -- read this as "no regression," not as a
quality win the cost optimizations are responsible for: it's well within
the ~1.16-2.83pp run-to-run noise this project has repeatedly measured on
identical configs (temperature was never pinned -- still open, §9). Field-
level accuracy actually moved in both directions between the two runs
(first_name 93.25% -> 96.25%, last_name 95.08% -> 92.67%) while the total
stayed roughly flat -- exactly the shape of ordinary non-determinism, not
a systematic effect of any single change here.

Preserved the cold run's own `cache.json`/`output.csv`/`failures.csv` as
`backups/*.combined_cold_run_result` for inspection, then restored the live
`cache.json` to its pre-test, accumulated state (this was a measurement
run, not intended to replace the project's accumulated learned cache with
a smaller one rebuilt from scratch). All of this session's other
before/after snapshots live in `backups/` too, moved there in a pass to
keep the project root readable -- see that folder's contents for the full
list, none of them are read by any script.

**This is the number that belongs in SUBMISSION.md §2**, and has been
copied there: $0.0088/1,000 names, ~$0.91/month projected (same Heaps'-law
method as before, updated cost-per-token: $0.0000218 vs the original
$0.0000468-$0.0000487), 89.67% accuracy. The cache-correction pass
(log #11) still has not been redone against this current pipeline --
flagged in SUBMISSION.md §2 rather than silently assumed to still be
98.58%.

**Cost of this measurement:** $0.0106 (the combined cold run itself --
this measurement doubles as the result it's measuring, no separate
diagnostic cost on top).
