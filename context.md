# Context: Welcome Home name-translation cost review

Purpose of this file: a complete handoff so another AI (or a human) can pick up this
project cold, without re-reading every file. Written 2026-08-13 from a review of the
current repo state — code, git history, and docs — not just the docs.

---

## 1. The task, in one paragraph

Nimbus Retail's "Welcome Home" loyalty programme greets every customer by name, in
whichever of English/Arabic they *didn't* sign up in (so it has to transliterate/translate
names). The as-launched implementation calls `gemini-2.5-pro` once per name, unbatched,
uncached, and nobody has checked its cost since launch. The assignment: find the cheapest
way to run this that Marketing will still accept, given two real constraints — **up to 30
hours latency is fine** (translation is not real-time; it runs on a scheduled batch cycle),
and **quality has no fixed threshold**, only "a customer must never see their own name
written wrong," which has to be defended with evidence, not assumed. Full brief:
`README.md`. Grading rubric and template: `SUBMISSION.md` (already filled in — see §3).
Volume: ~86,400 signups/day in production; the test sample is 1,200 records
(`data/data/names_input.csv` + held-out `data/data/gold.csv`).

Hard rules from the brief (still binding if this work continues):
- `gold.csv` is for scoring only — the pipeline must never read it to translate.
- Must be re-runnable against an unseen set of names.
- Must justify the numbers at 86,400/day, not just 1,200.
- Every experiment's cost — including failed ones — is part of the deliverable.

---

## 2. Repo layout

This directory (`CostOptimizationTask/`) is its own git repo (3 commits: `first commit`,
`... MaxOutput tokens + Minimal ThinkingLevel + new optimal prompt`, `prompt v2` — the last
one is **not what its name implies**, see §5).

```
README.md              task brief (read this first for the business framing)
SUBMISSION.md          the filled-in deliverable — recommendation, numbers, experiment log
EXPERIMENT_LOG.md       staging notes the numbers in SUBMISSION.md were drafted from
score.py                the grader (given, do not modify semantics of)
preprocess.py           production pipeline stage 1: cache lookup, dedup, chunk into requests
translate.py             production pipeline stage 2: calls Gemini, updates cache, writes output.csv
probe_25_models.py      quick reachability check for the three gemini-2.5-* models on a key
data/data/
  names_input.csv        1,200-row sample input
  gold.csv                reference answers (never read by the pipeline itself)
cache.json               persistent name-translation cache (bidirectional + gender)
batch_plan.json          preprocess.py's output — the request plan translate.py consumes
output.csv, failures.csv  last real run's output + score.py's diff
backups/                 pre-change snapshots of cache.json/output.csv/failures.csv from
                           this session's experiments — not read by any script, purely a
                           safety net; moved here to keep the root readable
gender_lookup.py, gender_classifier.py, experiments/    see EXPERIMENT_LOG.md --
  significant work has landed since this file was written (gender-inference tiers,
  JSON-array response format, a caching investigation); this file is stale on those
  and describes the state as of 2026-08-13, not the current pipeline
experiments/
  requirements.txt
  pipeline/               a separate, more rigorous bake-off harness (see §6)
  runs/                    timestamped bake-off outputs (predictions, summaries)
```

Two pipelines exist side by side:
1. **Production pipeline** (`preprocess.py` + `translate.py`, repo root) — what actually
   ships and what SUBMISSION.md's numbers describe.
2. **Bake-off harness** (`experiments/pipeline/`) — used to compare models/prompts
   head-to-head with proper cost/accuracy measurement (McNemar test, per-stratum
   accuracy). Not what ships; used to generate the evidence behind the recommendation.

---

## 3. Current recommendation (per SUBMISSION.md)

Replace the `gemini-2.5-pro`, one-call-per-name baseline with:
- **`gemini-3.1-flash-lite`** (cheapest of the reachable models *and* most accurate —
  counterintuitive but measured, see §6),
- a **persistent cross-run cache** (`cache.json`, keyed on NFC-normalized/casefolded text),
- a **closed deterministic lookup table** for the 18 known prefix forms (Dr./Mrs./Sheikh/…),
  LLM as fallback only for unknown ones,
- **50-name batched prompts** (`chunk_size=50`, picked from a single-draw sweep of
  25/50/100 — cost drops monotonically with chunk size, accuracy did not, see §6 exp #15).

**Measured**: 89.33% whole-record accuracy (1,072/1,200), $0.0198/1,000 names, cold cache.
**Plus a one-time, zero-marginal-cost step**: hand-correct the ~30 most frequent recurring
failure patterns directly in the cache (justified because failures are heavy-tailed — top
30 patterns cover 91.5% of all failures) → measured 98.58% (1,183/1,200) at $0 extra spend.
Projected monthly cost at 86,400/day: **~$1.95** (projection method and caveats in
SUBMISSION.md §2 — token volume at scale is extrapolated via a Heaps'-law fit, not measured).

**The baseline (`gemini-2.5-pro`, today's actual pipeline) was never successfully
measured** — every attempt across 3 API keys hit a 404 or a 0-quota 429. This is reported
as an open gap in SUBMISSION.md, not papered over. If this work continues, resolving
billing/quota access to get that number is the single highest-value next step besides §5
below.

Full reasoning, all 15 logged experiments (including dead ends — batch API access never
worked, a schema bug, a botched first correction-pass attempt), rejected alternatives, and
known scale risks: **read `SUBMISSION.md` in full — it is the primary source of truth for
what was tried and why**, this file only orients you around it.

---

## 4. How to run it

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="..."          # or $env:GEMINI_API_KEY in PowerShell

python preprocess.py                  # reads data/data/names_input.csv + cache.json,
                                       # writes batch_plan.json (+ batch_<dir>.jsonl)
python translate.py --sync            # calls Gemini, updates cache.json, writes output.csv
                                       # --sync is required: batches.create was denied on
                                       # every key tried (see §6) — the Batch API code path
                                       # exists but has never been exercised end-to-end.
python score.py output.csv --gold data/data/gold.csv
                                       # NOTE: score.py's own --gold default is "data/gold.csv"
                                       # (no second "data/"), which does NOT match this
                                       # repo's actual data/data/gold.csv path. Always pass
                                       # --gold explicitly, or the default will 404.
```

Verified during this review: current `output.csv` scores **89.33%** (1,072/1,200) — this
is the chunk_size=50 cold-cache run from SUBMISSION.md §6 exp #15, not the 98.58%
correction-pass state (which, per SUBMISSION.md §6 exp #14, was lost when a later cache
reset overwrote it and was never redone — `cache.json` currently contains no evidence of
the correction pass).

---

## 5. ⚠️ Unresolved discrepancy between code and docs — read before trusting a re-run

`SUBMISSION.md` §4 documents a 9-rule "v2" style prompt as "final version, from
`preprocess.py`'s `STYLE_RULES` constant" and credits it for specific accuracy gains
(hamza/ta-marbuta stratum +3.7pp, etc.), with a v1-vs-v2 comparison table.

**That prompt is not what `preprocess.py` currently contains.** The repo's last commit —
titled `prompt v2`, dated 2026-08-13 (today) — deleted the 9-rule block and replaced it
with:

```python
STYLE_RULES = """\
-Transliterate personal names between English and Arabic. Output only the transliteration itself, never leave a field blank.
"""
```

This is a *regression*, not an upgrade, despite the commit name — it's less detailed than
even the "v1" prompt SUBMISSION.md describes. Every accuracy number in SUBMISSION.md and
EXPERIMENT_LOG.md (89.33%, 98.58%, the v1/v2 comparison) was measured under the old
9-rule prompt. **A fresh run of `preprocess.py` + `translate.py` today will use the
one-line prompt and will not reproduce those numbers.**

The full 9-rule prompt text still exists, byte-for-byte, in
`experiments/pipeline/prompts.py`'s `STYLE_RULES` (the bake-off harness never lost it).
If continuing this work, the first move should be deciding whether this was an accidental
revert (most likely — the commit message and the diff don't match) and, if so, restoring
`preprocess.py`'s `STYLE_RULES` from `experiments/pipeline/prompts.py` before doing
anything else that depends on accuracy numbers matching the submission.

---

## 6. Key findings worth knowing before re-deriving them

- **Cheapest model won on accuracy too.** `gemini-3.1-flash-lite` beat both
  `gemini-3.5-flash-lite` and `gemini-3.6-flash` on accuracy while being the cheapest of
  the three — not a cost/quality tradeoff in this case, verified via bake-off.
- **Model availability had to be probed per-key, not trusted from docs.**
  `gemini-2.5-flash-lite` 404'd ("no longer available to new users"), `gemini-2.5-pro`
  429'd at 0 quota — on every key tried. `probe_25_models.py` exists for exactly this check.
- **Batch API (`batches.create`) was denied at the project level on every key tried** —
  consistent 403/400, looks like it requires GCP billing enabled. Every real run in this
  project used `--sync` (standard `generate_content`, no batch discount). The 50% batch
  discount in the cost math is aspirational, not realized.
- **Failures are heavy-tailed, not evenly spread**: 141 real failures collapsed to 40
  distinct (field, expected, got) patterns; top 5 = 31.2% of all failures, top 30 = 91.5%.
  This is *why* the cache-correction-pass strategy works and scales (a fixed review budget
  captures most of the value regardless of volume) — see SUBMISSION.md §9 for the proposed
  `review.py` follow-up tool that was never built.
- **Zero hallucinations across every failure hand-checked** (65 bake-off failures + 141 real
  ones) — every mismatch was a legitimate alternate transliteration, not garbage. This is
  the evidentiary basis for "the model is good enough," which is the quality argument
  Marketing needs.
- **`temperature` was never pinned** — ~1.16–2.83pp run-to-run swing observed on identical
  configs. Listed as a priority fix in SUBMISSION.md §9 but not done.
- **Chunk-size sweep (25/50/100) is a single draw per size**, not statistically confirmed —
  cost drops monotonically with chunk size, accuracy did not, and the spread exceeds
  known run-to-run noise. 50 was kept as the shipped default on "best measured + it's what
  the retry logic was tuned against," explicitly flagged as not proven optimal.
- **`cache.json` conflates disposable model output with irreplaceable human corrections**,
  single file, single writer — flagged as the top structural risk at production scale
  (SUBMISSION.md §8). This is exactly what caused the 98.58%→89.33% regression described
  above in the data (a "clear cache for a clean baseline" op silently destroyed the
  correction pass, with no separate backup). If continuing this work, splitting the cache
  into a disposable model-response store and an append-only human-override table is called
  out as necessary before any concurrent/production deployment.

---

## 7. What's explicitly still open (from SUBMISSION.md §9, condensed)

1. Redo the cache-correction pass (§6 exp #11) and protect it in a separate store this time.
2. Resolve billing/quota to measure the real `gemini-2.5-pro` baseline and to actually
   exercise the Batch API end-to-end (currently only sync has ever run).
3. Turn the correction pass into a repeatable weekly tool (`review.py`, sketched but unbuilt).
4. Pin `temperature=0`.
5. A/B the glossary-injection prompt (`experiments/pipeline/glossary.py` — built, wired into
   the bake-off harness's `--glossary` flag, never conclusively evaluated against the
   9-rule-only prompt) on the full sample.
6. A proper multi-trial chunk-size sweep (§6 above) — currently n=1 per size.

Plus, from this review: **resolve §5 first** — none of the other numbers are trustworthy to
reproduce until the shipped prompt matches what's documented.
