#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import json
import os
import time

from preprocess import (norm_key, load_cache, save_cache, MODEL_NAME,
                          response_schema_for, MAX_OUTPUT_TOKENS)


PRICE_IN = 0.25
PRICE_OUT = 1.50
BATCH_DISCOUNT = 0.5


def get_client():
    from google import genai
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set.")
    return genai.Client(api_key=key)


def run_batch(client, jsonl_path, direction):
    from google.genai import types
    uploaded = client.files.upload(
        file=jsonl_path,
        config=types.UploadFileConfig(mime_type="application/jsonl"))
    job = client.batches.create(
        model=MODEL_NAME, src=uploaded.name,
        config={"display_name": f"welcome-home-{direction}"})
    print(f"  submitted {direction} batch job: {job.name}")
    terminal = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED",
                 "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}
   
    wait, waited = 20, 0
    while job.state.name not in terminal:
        time.sleep(wait)
        waited += wait
        wait = min(wait * 1.5, 300)
        job = client.batches.get(name=job.name)
        print(f"    ... {job.state.name} ({waited // 60}m elapsed)")
    if job.state.name != "JOB_STATE_SUCCEEDED":
        raise RuntimeError(f"{direction} batch job ended in {job.state.name}")
    raw = client.files.download(file=job.dest.file_name)
    out = {}  
    usage = []
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        try:
            resp = rec["response"]
            u = resp.get("usageMetadata", {})
            usage.append({
                "prompt_tokens": u.get("promptTokenCount", 0),
                "output_tokens": u.get("candidatesTokenCount", 0),
                "thinking_tokens": u.get("thoughtsTokenCount", 0),
            })
            text = resp["candidates"][0]["content"]["parts"][0]["text"]
            out[rec["key"]] = json.loads(text)
        except Exception as e:  
            print(f"  WARNING: could not parse response for {rec.get('key')}"
                  f" -- {str(e)[:200]}")
    return out, usage


def run_sync(client, direction, chunks):
    """chunks: {chunk_index_str: {id_str: {norm_key, src, slot,
    known_gender}}}. Rebuilds each chunk's prompt and calls
    generate_content directly -- used when batches.create is denied at the
    project level. known_gender may be absent on older/retry chunk dicts
    (treated as None, i.e. "ask the LLM") rather than raising."""
    from preprocess import build_prompt
    out = {}
    usage = []
    for ci, items in chunks.items():
        ordered = sorted(items.items(), key=lambda kv: int(kv[0]))
        request_items = [(int(i), v["src"], v["slot"], v.get("known_gender"))
                           for i, v in ordered]
        prompt = build_prompt(direction, request_items)
        key = f"{direction}-{ci}"
        try:
            resp = client.models.generate_content(
                model=MODEL_NAME, contents=prompt,
                config={"thinkingConfig": {"thinkingLevel": "MINIMAL"},
                         "responseMimeType": "application/json",
                         "responseSchema": response_schema_for(direction),
                         "maxOutputTokens": MAX_OUTPUT_TOKENS})
            out[key] = json.loads(resp.text)
            u = resp.usage_metadata
            usage.append({
                "prompt_tokens": getattr(u, "prompt_token_count", 0) or 0,
                "output_tokens": getattr(u, "candidates_token_count", 0) or 0,
                "thinking_tokens": getattr(u, "thoughts_token_count", 0) or 0,
            })
        except Exception as e:  # noqa: BLE001 -- log and skip, same as batch path
            print(f"  WARNING: sync call failed for {key} -- {str(e)[:200]}")
    return out, usage


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="batch_plan.json")
    ap.add_argument("--cache", default="cache.json")
    ap.add_argument("--names-input", default="data/data/names_input.csv")
    ap.add_argument("--out", default="output.csv")
    ap.add_argument("--sync", action="store_true",
                      help="use generate_content instead of the Batch API")
    args = ap.parse_args()

    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)
    names, gender = load_cache(args.cache)

    client = None
    if plan["directions"]:
        client = get_client()

    def absorb(meta, item):
        src, gtext = meta["src"], item.get("text", "")
        names[norm_key(src)] = gtext
        names[norm_key(gtext)] = src
        g = item.get("gender")
        if g:
            gender[norm_key(src)] = g
            gender[norm_key(gtext)] = g

    def iter_results(resp):
        """resp["results"] is a list of [id, text, gender] triples for
        en2ar, or [id, text] pairs for ar2en -- ar2en has no gender slot at
        all (RESPONSE_SCHEMA_AR2EN, Task #9), since AR_TO_EN_PREFIX already
        disambiguates gender from the Arabic prefix word itself and never
        reads this field. Yields (rid, item_dict) so the rest of this file
        can keep using absorb() unchanged either way (item.get("gender")
        naturally returns None for a 2-element entry). A malformed entry
        (not exactly 2 or 3 elements) is skipped, not raised -- it falls
        through to the same missing-id retry path as a genuinely absent
        id, rather than crashing the whole chunk."""
        for entry in resp.get("results", []):
            if not isinstance(entry, list) or len(entry) not in (2, 3):
                continue
            rid, text = entry[0], entry[1]
            item = {"text": text}
            if len(entry) == 3:
                item["gender"] = entry[2]
            yield str(rid), item

    all_usage = [] 

    for direction, dinfo in plan["directions"].items():
        print(f"=== {direction} ===")
        if args.sync:
            chunks_by_index = {str(i): items
                                 for i, items in enumerate(dinfo["chunks"])}
            responses, usage = run_sync(client, direction, chunks_by_index)
        else:
            responses, usage = run_batch(client, dinfo["jsonl_path"], direction)
        all_usage.extend(usage)

        leftover = {}  
        for ci, items in enumerate(dinfo["chunks"]):
            key = f"{direction}-{ci}"
            resp = responses.get(key)
            if not resp:
                print(f"  WARNING: no response at all for chunk {ci} "
                      f"({len(items)} tokens -- queued for retry)")
                leftover.update({v["norm_key"]: v for v in items.values()})
                continue
            seen = set()
            for rid, item in iter_results(resp):
                meta = items.get(rid)
                if meta is None:
                    continue
                seen.add(rid)
                absorb(meta, item)
            missing = set(items) - seen
            if missing:
                leftover.update({items[rid]["norm_key"]: items[rid]
                                   for rid in missing})

        
        chunk_size = plan.get("chunk_size", 50)
        for attempt in range(2):
            if not leftover:
                break
            print(f"  retry {attempt + 1}: {len(leftover)} unresolved "
                  f"token(s) for {direction}")
            leftover_list = list(leftover.items())  
            retry_chunks = {
                f"retry{ci}": {str(i): meta for i, (_, meta) in enumerate(group)}
                for ci, group in enumerate(
                    leftover_list[i:i + chunk_size]
                    for i in range(0, len(leftover_list), chunk_size))
            }
            retry_responses, retry_usage = run_sync(client, direction, retry_chunks)
            all_usage.extend(retry_usage)
            seen = set()
            for ci, group_items in retry_chunks.items():
                resp = retry_responses.get(f"{direction}-{ci}")
                if not resp:
                    continue
                for rid, item in iter_results(resp):
                    meta = group_items.get(rid)
                    if meta is None:
                        continue
                    seen.add(meta["norm_key"])
                    absorb(meta, item)
            leftover = {k: v for k, v in leftover.items() if k not in seen}

        if leftover:
            print(f"  WARNING: {len(leftover)} token(s) still unresolved "
                  f"for {direction} after retries -- will pass through "
                  f"untranslated in the output CSV.")

    save_cache(args.cache, names, gender)
    print(f"\ncache updated: {len(names)} entries -> {args.cache}")

    if all_usage:
        tok_in = sum(u["prompt_tokens"] for u in all_usage)
        tok_out = sum(u["output_tokens"] for u in all_usage)
        tok_think = sum(u["thinking_tokens"] for u in all_usage)
        discount = 1.0 if args.sync else BATCH_DISCOUNT
        cost = (tok_in / 1e6 * PRICE_IN
                 + (tok_out + tok_think) / 1e6 * PRICE_OUT) * discount
        rate_label = "standard rate, --sync" if args.sync else "batch rate"
        print(f"\nAPI cost this run: ${cost:.4f} [{rate_label}]  "
              f"({len(all_usage)} requests, in={tok_in}, out={tok_out}, "
              f"thinking={tok_think} tokens)")
        print("  (PRICE_IN/PRICE_OUT verified against "
              "https://ai.google.dev/gemini-api/docs/pricing on 2026-08-12 "
              "-- re-check if citing this figure much later, rates change)")

    resolved_prefix = plan["resolved_prefix"]

    
    with open(args.names_input, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    row_by_id = {r["record_id"]: r for r in rows}

    en_to_ar_gendered = {
        "dr.": ("الدكتور", "الدكتورة"),
        "prof.": ("الأستاذ الدكتور", "الأستاذة الدكتورة"),
        "eng.": ("المهندس", "المهندسة"),
    }
    unresolved_gender = []
    for rid, pkey in plan["pending_gendered_prefix"].items():
        fn = row_by_id[rid]["first_name"]
        g = gender.get(norm_key(fn))
        male, female = en_to_ar_gendered[pkey]
        if g == "F":
            resolved_prefix[rid] = female
        elif g == "M":
            resolved_prefix[rid] = male
        else:
            resolved_prefix[rid] = male  
            unresolved_gender.append(rid)
    if unresolved_gender:
        print(f"WARNING: {len(unresolved_gender)} record(s) had a gendered "
              f"prefix but no resolvable gender -- defaulted to the male "
              f"form. record_ids: {unresolved_gender[:10]}")

    
    for rid, val in resolved_prefix.items():
        if val is not None:
            continue
        src_prefix = (row_by_id[rid].get("prefix") or "").strip()
        translated = names.get(norm_key(src_prefix))
        resolved_prefix[rid] = translated if translated else src_prefix

    # -- assemble the graded CSV --
    out_rows = []
    n_missing_names = 0
    for row in rows:
        rid = row["record_id"]
        fn = row.get("first_name") or ""
        ln = row.get("last_name") or ""
        t_fn = names.get(norm_key(fn), fn)
        t_ln = names.get(norm_key(ln), ln)
        if t_fn == fn and fn:
            n_missing_names += 1
        out_rows.append({
            "record_id": rid,
            "prefix": resolved_prefix.get(rid, ""),
            "first_name": t_fn,
            "last_name": t_ln,
        })

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["record_id", "prefix",
                                            "first_name", "last_name"])
        w.writeheader()
        w.writerows(out_rows)

    if n_missing_names:
        print(f"\nWARNING: {n_missing_names} field(s) had no cache entry "
              f"and were passed through untranslated -- check for a failed "
              f"chunk above.")
    print(f"\n{len(out_rows)} records written to {args.out}")
    print(f"next: python score.py {args.out}")


if __name__ == "__main__":
    main()
