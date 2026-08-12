# Bake-off harness

## Setup

```bash
pip install -r requirements.txt
```

Set your key as an environment variable (never paste it into a file or the
command line where it could get committed or logged):

**PowerShell**
```powershell
$env:GEMINI_API_KEY = "your-key-here"
```

**Bash**
```bash
export GEMINI_API_KEY="your-key-here"
```

## Step 1 -- dry run (free, no key needed)

```bash
python -m pipeline.bakeoff --dry-run
```

Builds the full JSONL request files for all three models against the entire
487-token pool, prints request/token counts, and writes the `.jsonl` files to
`runs/<timestamp>_<model>/` so you can eyeball them before spending anything.

## Step 2 -- the real bake-off

```bash
python -m pipeline.bakeoff
```

Runs all three models (`gemini-2.5-flash-lite`, `gemini-3.1-flash-lite`,
`gemini-2.5-pro`) via the Batch API over the full token pool, scores each
against `gold.csv`, prints per-stratum accuracy (overall / ar2en / en2ar /
en2ar-critical-orthography / particle-bearing / singleton), a paired McNemar
comparison between every model pair, and a cost ledger built from real
`usage_metadata` -- not estimates.

Batch jobs can take up to ~24h to complete (usually faster); the script
polls every 30s and persists the job name to disk so a crash/restart resumes
rather than resubmitting and double-paying.

Add `--glossary` to run prompt v2 (house-style glossary injected, built only
from `names_input.csv` -- never from gold). Compare v1 vs v2 spread across
models to see how much of the accuracy gap prompt engineering closes.

Run one model at a time with `--models gemini-2.5-pro` if you want to spend
incrementally rather than all three at once.

## Output

- `runs/<timestamp>_<model>/predictions.json` -- every token this model
  resolved, plus inferred gender for first names.
- `runs/<timestamp>_summary.json` -- cost + per-stratum accuracy for every
  model run, machine-readable for pulling into the submission.

## Notes / things to verify before trusting the numbers

- Prices in `pipeline/models.py` are from web research this session, not a
  live pricing call -- re-check https://ai.google.dev/gemini-api/docs/pricing.
- `gemini-2.5-pro` has no documented way to fully disable thinking (no
  `thinkingBudget=0` support confirmed) -- its thinking-token count is exactly
  the number this harness measures for you; don't assume a value.
- If any chunk comes back with missing ids, the script logs a warning and
  leaves those tokens unresolved rather than silently failing the run. In
  the production pipeline (not this bake-off) those get re-queued.
