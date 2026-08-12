# -*- coding: utf-8 -*-
"""Run the 3-model bake-off over the full distinct-token pool.

Usage:
    python -m pipeline.bakeoff --dry-run                 # build+validate, no API calls, no cost
    python -m pipeline.bakeoff                            # the real thing (needs GEMINI_API_KEY)
    python -m pipeline.bakeoff --models gemini-2.5-pro     # just one model
    python -m pipeline.bakeoff --glossary                 # prompt v2 (house-style glossary)

Always try --dry-run first. It builds every JSONL file, prints request/token
counts, and validates the pipeline end to end for $0.
"""
import argparse
import json
import os
import time

from .common import key as normkey
from .eval import build_token_pool, score_pool, mcnemar
from .fuzzy import classify_failures, summarize_failures
from .glossary import build_glossaries, glossary_block
from .models import MODEL_CONFIGS
from .cost import summarize

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "data")
RUN_DIR = os.path.join(os.path.dirname(__file__), "..", "runs")


def chunk(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def build_chunks(pool, chunk_size):
    """Groups pool tokens into same-direction chunks of `chunk_size`,
    each item tagged with a stable integer id for reconciliation."""
    by_dir = {"ar2en": [], "en2ar": []}
    for k, v in pool.items():
        by_dir[v["direction"]].append((k, v["src"], v["slot"]))
    chunks = {}
    for direction, items in by_dir.items():
        items.sort(key=lambda t: t[0])  # stable order run-to-run
        numbered = [(i, tok, slot) for i, (k, tok, slot) in enumerate(items)]
        id_to_key = {i: k for i, (k, tok, slot) in enumerate(items)}
        chunks[direction] = {
            "chunks": list(chunk(numbered, chunk_size)),
            "id_to_key": id_to_key,
        }
    return chunks


def run_model(model_name, chunks, glossary_terms, use_glossary, run_dir, dry_run,
              mode="batch"):
    from .batch_client import (get_client, build_jsonl, resume_or_submit,
                                poll_until_done, download_results)
    from .prompts import build_prompt

    os.makedirs(run_dir, exist_ok=True)
    predictions = {}   # normkey(src) -> predicted text
    genders = {}        # normkey(src) -> "M"/"F"/""
    usages = []
    total_requests = 0

    client = None if dry_run else get_client()

    for direction, payload in chunks.items():
        chunk_list = payload["chunks"]
        id_to_key = payload["id_to_key"]
        term_str = glossary_block(glossary_terms[direction]) if use_glossary else None
        total_requests += len(chunk_list)
        n_tokens = sum(len(c) for c in chunk_list)

        if mode == "sync":
            print(f"  [{model_name}] {direction}: {len(chunk_list)} sync calls, "
                  f"{n_tokens} tokens")
            if dry_run:
                continue
            from .sync_client import run_sync_chunk
            seen_ids = set()
            for c in chunk_list:
                prompt = build_prompt(direction, c, term_str, use_glossary)
                try:
                    parsed, usage = run_sync_chunk(client, model_name, prompt)
                except Exception as e:  # noqa: BLE001 -- log and keep going;
                                          # one bad chunk shouldn't kill the run
                    print(f"  WARNING: sync call failed for a {direction} "
                          f"chunk -- {str(e).splitlines()[0][:500]}")
                    continue
                usages.append(usage)
                for item in parsed.get("results", []):
                    rid = item.get("id")
                    if rid is None or rid not in id_to_key:
                        continue
                    seen_ids.add(rid)
                    src_key = id_to_key[rid]
                    predictions[src_key] = item.get("text", "")
                    if item.get("gender"):
                        genders[src_key] = item["gender"]
            missing = set(id_to_key) - seen_ids
            if missing:
                print(f"  WARNING: {len(missing)} ids missing from {direction} "
                      f"sync responses for {model_name} -- left unresolved.")
            continue

        # -- batch mode --
        jsonl_path = os.path.join(run_dir, f"{model_name}_{direction}.jsonl")
        km = build_jsonl(chunk_list, model_name, direction, term_str,
                          use_glossary, jsonl_path)

        print(f"  [{model_name}] {direction}: {len(chunk_list)} requests, "
              f"{n_tokens} tokens -> {jsonl_path}")

        if dry_run:
            continue

        job_file = os.path.join(run_dir, f"{model_name}_{direction}.job.json")
        job = resume_or_submit(client, jsonl_path, model_name,
                                f"bakeoff-{model_name}-{direction}", job_file)
        job = poll_until_done(client, job)
        results = download_results(client, job)

        seen_ids = set()
        for entry in results:
            if entry["usage"]:
                usages.append(entry["usage"])
            resp = entry.get("response")
            if not resp:
                continue
            for item in resp.get("results", []):
                rid = item.get("id")
                text = item.get("text", "")
                gender = item.get("gender", "")
                if rid is None or rid not in id_to_key:
                    continue
                seen_ids.add(rid)
                src_key = id_to_key[rid]
                predictions[src_key] = text
                if gender:
                    genders[src_key] = gender

        missing = set(id_to_key) - seen_ids
        if missing:
            print(f"  WARNING: {len(missing)} ids missing from {direction} "
                  f"response for {model_name} -- would re-queue in production; "
                  f"left unresolved in this run.")

    return predictions, genders, usages, total_requests


# Confirmed working on the current key (probe_all): cheap / mid / upper 3.x bracket.
ORIGINAL_THREE = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.6-flash"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=ORIGINAL_THREE,
                     choices=list(MODEL_CONFIGS))
    ap.add_argument("--chunk-size", type=int, default=50)
    ap.add_argument("--glossary", action="store_true",
                     help="use prompt v2 (house-style glossary injected)")
    ap.add_argument("--dry-run", action="store_true",
                     help="build and validate requests, call no API, spend $0")
    ap.add_argument("--sync", action="store_true",
                     help="use synchronous generate_content instead of the "
                          "Batch API (fallback for when batches.create is "
                          "denied at the project level). Cost is reported at "
                          "standard rate; batch price is shown alongside as "
                          "a documented projection, not a measurement.")
    ap.add_argument("--names-input", default=os.path.join(DATA_DIR, "names_input.csv"))
    ap.add_argument("--gold", default=os.path.join(DATA_DIR, "gold.csv"))
    ap.add_argument("--run-dir", default=RUN_DIR)
    args = ap.parse_args()

    pool = build_token_pool(args.names_input, args.gold)
    print(f"token pool: {len(pool)} distinct tokens "
          f"({sum(1 for v in pool.values() if v['direction']=='ar2en')} ar2en, "
          f"{sum(1 for v in pool.values() if v['direction']=='en2ar')} en2ar)")

    en_terms, ar_terms = build_glossaries(args.names_input)
    glossary_terms = {"ar2en": en_terms, "en2ar": ar_terms}

    chunks = build_chunks(pool, args.chunk_size)

    all_results = {}
    report_rows = []
    failed_models = []
    stamp = time.strftime("%Y%m%d-%H%M%S")

    for model_name in args.models:
        run_dir = os.path.join(args.run_dir, f"{stamp}_{model_name}")
        print(f"\n=== {model_name} ({MODEL_CONFIGS[model_name]['role']}) ===")
        try:
            preds, genders, usages, n_req = run_model(
                model_name, chunks, glossary_terms, args.glossary, run_dir,
                args.dry_run, mode="sync" if args.sync else "batch")
        except Exception as e:  # noqa: BLE001 -- one dead model must not
                                  # take the other models' results down with it
            print(f"  FAILED: {model_name} -- {str(e).splitlines()[0][:500]}")
            print(f"  skipping {model_name}, continuing with remaining models.")
            failed_models.append(model_name)
            continue

        if args.dry_run:
            continue

        report, results = score_pool(pool, preds)
        all_results[model_name] = results
        cost = summarize(model_name, usages, batch=not args.sync)

        rate_label = "standard rate (--sync)" if args.sync else "batch rate"
        print(f"  requests: {n_req}   cost: ${cost['cost_usd']:.4f} [{rate_label}]   "
              f"(in={cost['tokens_in']}, out={cost['tokens_out']}, "
              f"thinking={cost['tokens_thinking']})")
        if args.sync:
            projected = summarize(model_name, usages, batch=True)
            print(f"    -> projected batch-rate cost (not measured): "
                  f"${projected['cost_usd']:.4f}")
        for stratum, r in report.items():
            print(f"    {stratum:16s} {r['hits']:4d}/{r['n']:<4d} "
                  f"{r['accuracy']:.1%}")

        failures = classify_failures(pool, preds, results)
        fsum = summarize_failures(failures)
        if fsum["total_failed"]:
            print(f"    [diagnostic, not part of the score] of "
                  f"{fsum['total_failed']} failed tokens: "
                  f"{fsum['near_miss']} near-miss (<=1 char off, likely "
                  f"orthography), {fsum['far_miss']} far-miss (wrong name)")

        report_rows.append({"model": model_name, **cost, "report": report,
                             "failure_diagnostic": fsum})
        with open(os.path.join(run_dir, "predictions.json"), "w", encoding="utf-8") as f:
            json.dump({"predictions": preds, "genders": genders}, f, ensure_ascii=False)

    if failed_models:
        print(f"\n!! {len(failed_models)} model(s) failed and were skipped: "
              f"{', '.join(failed_models)}")
        print("   Results below only cover the models that succeeded.")

    if not args.dry_run and len(all_results) >= 2:
        print("\n=== paired comparison (McNemar) ===")
        names = list(all_results)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                m = mcnemar(all_results[a], all_results[b])
                print(f"  {a} vs {b}: n={m['n']}  "
                      f"{a} only right={m['a_right_b_wrong']}  "
                      f"{b} only right={m['b_right_a_wrong']}  "
                      f"both right={m['both_right']}")

    if not args.dry_run and report_rows:
        print("\n" + "=" * 78)
        print("  FINAL COMPARISON")
        print("=" * 78)
        header = f"  {'model':<24}{'cost':>10}{'overall':>10}{'critical':>10}{'/1000*':>12}"
        print(header)
        print("  " + "-" * 74)
        for row in report_rows:
            overall = row["report"]["overall"]["accuracy"]
            critical = row["report"]["en2ar_critical"]["accuracy"]
            n_tokens = row["report"]["overall"]["n"]
            per_1000 = row["cost_usd"] / n_tokens * 1000 if n_tokens else 0.0
            print(f"  {row['model']:<24}{'$'+format(row['cost_usd'],'.4f'):>10}"
                  f"{overall:>10.1%}{critical:>10.1%}{'$'+format(per_1000,'.4f'):>12}")
        print("  " + "-" * 74)
        print("  *cost/1000 is per 1,000 DISTINCT TOKENS in this bake-off, not per "
              "1,000 records --\n   scale it by your measured records-per-1000-tokens "
              "ratio for the submission table.")
        print("=" * 78)

        summary_path = os.path.join(args.run_dir, f"{stamp}_summary.json")
        summary_csv = os.path.join(args.run_dir, f"{stamp}_summary.csv")
        os.makedirs(args.run_dir, exist_ok=True)
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(report_rows, f, indent=2, ensure_ascii=False)
        with open(summary_csv, "w", encoding="utf-8", newline="") as f:
            import csv as _csv
            w = _csv.writer(f)
            w.writerow(["model", "requests", "tokens_in", "tokens_out",
                        "tokens_thinking", "cost_usd", "overall_accuracy",
                        "critical_accuracy", "cost_per_1000_tokens"])
            for row in report_rows:
                overall = row["report"]["overall"]["accuracy"]
                critical = row["report"]["en2ar_critical"]["accuracy"]
                n_tokens = row["report"]["overall"]["n"]
                per_1000 = row["cost_usd"] / n_tokens * 1000 if n_tokens else 0.0
                w.writerow([row["model"], row["requests"], row["tokens_in"],
                            row["tokens_out"], row["tokens_thinking"],
                            row["cost_usd"], overall, critical, per_1000])
        print(f"\nsummary written to {summary_path}")
        print(f"summary (csv, paste-ready) written to {summary_csv}")


if __name__ == "__main__":
    main()
