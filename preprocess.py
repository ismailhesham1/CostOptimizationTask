#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import json
import os
import re
import unicodedata

MODEL_NAME = "gemini-3.1-flash-lite"  # picked from the testing


_WHITESPACE = re.compile(r"\s+")


def norm_key(s):
    text = unicodedata.normalize("NFC", s or "")
    return _WHITESPACE.sub(" ", text).strip().casefold()


def is_arabic(s):
    return any("؀" <= c <= "ۿ" for c in (s or ""))



AR_TO_EN_PREFIX = {
    "": "",
    norm_key("الدكتور"): "Dr.", norm_key("الدكتورة"): "Dr.",
    norm_key("الأستاذ الدكتور"): "Prof.", norm_key("الأستاذة الدكتورة"): "Prof.",
    norm_key("المهندس"): "Eng.", norm_key("المهندسة"): "Eng.",
    norm_key("السيد"): "Mr.", norm_key("السيدة"): "Mrs.",
    norm_key("الشيخ"): "Sheikh", norm_key("الشيخة"): "Sheikha",
}

EN_TO_AR_PREFIX = {
    "": "",
    "mr.": "السيد", "mrs.": "السيدة",
    "sheikh": "الشيخ", "sheikha": "الشيخة",
    "dr.": ("الدكتور", "الدكتورة"),
    "prof.": ("الأستاذ الدكتور", "الأستاذة الدكتورة"),
    "eng.": ("المهندس", "المهندسة"),
}
GENDERED_PREFIXES = {"dr.", "prof.", "eng."}


STYLE_RULES = """\
-Transliterate personal names between English and Arabic. Output only the transliteration itself, never leave a field blank.
"""


MAX_OUTPUT_TOKENS = 4096

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "text": {"type": "string"},
                    "gender": {
                        "type": "string",
                        "description": (
                            "Only for first names: the person's apparent "
                            "gender inferred from the name, as 'M' or 'F'. "
                            "Leave as an empty string for last_name/prefix "
                            "entries or when gender cannot be inferred."
                        ),
                    },
                },
                "required": ["id", "text"],
            },
        },
    },
    "required": ["results"],
}


def build_prompt(direction, items):
    """items: list of (id, token, slot)."""
    src_lang = "Arabic" if direction == "ar2en" else "English"
    dst_lang = "English" if direction == "ar2en" else "Arabic"
    lines = [f'{{"id": {i}, "slot": "{slot}", "text": "{tok}"}}'
              for i, tok, slot in items]
    return (
        STYLE_RULES + "\n"
        f"Translate each of the following {src_lang} name fragments into "
        f"{dst_lang}. Return JSON matching the schema, one result per input "
        f"id. For entries whose slot is 'first_name', also infer gender "
        f"(M/F); leave gender empty for last_name and prefix entries.\n\n"
        "[\n  " + ",\n  ".join(lines) + "\n]"
    )


def load_cache(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("names", {}), data.get("gender", {})
    return {}, {}


def save_cache(path, names, gender):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"names": names, "gender": gender}, f, ensure_ascii=False)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--names-input", default="data/data/names_input.csv")
    ap.add_argument("--cache", default="cache.json")
    ap.add_argument("--chunk-size", type=int, default=50)
    ap.add_argument("--plan", default="batch_plan.json")
    args = ap.parse_args()

    with open(args.names_input, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    names, gender = load_cache(args.cache)
    if not os.path.exists(args.cache):
        save_cache(args.cache, names, gender)
        print(f"created empty cache at {args.cache}")

   #holds distinct nmes that are not already in the cache, for submission to the LLM
    misses = {"ar2en": {}, "en2ar": {}}  
    total_slots = 0
    n_true_cache_hits = 0   # occurrences already resolved by a PRIOR run
    for row in rows:
        for slot in ("first_name", "last_name"):
            src = (row.get(slot) or "").strip()
            if not src:
                continue
            total_slots += 1
            k = norm_key(src)
            if k in names:
                n_true_cache_hits += 1
                continue  
            direction = "ar2en" if is_arabic(src) else "en2ar"
            misses[direction].setdefault(k, (src, slot))

    # -- prefixes: deterministic table first, LLM fallback for the rest --
    resolved_prefix = {}          # record_id -> final prefix string
    pending_gendered = {}         # record_id -> "dr."/"prof."/"eng." (english key)
    for row in rows:
        rid = row["record_id"]
        src_prefix = (row.get("prefix") or "").strip()
        direction = "ar2en" if is_arabic(row.get("first_name") or "") else "en2ar"
        if direction == "ar2en":
            k = norm_key(src_prefix)
            if k in AR_TO_EN_PREFIX:
                resolved_prefix[rid] = AR_TO_EN_PREFIX[k]
            else:
                misses["ar2en"].setdefault(
                    f"__prefix__{k}", (src_prefix, "prefix"))
                resolved_prefix[rid] = None  # fixed up after translate.py runs
        else:
            k = norm_key(src_prefix)
            if k == "":
                resolved_prefix[rid] = ""
            elif k in GENDERED_PREFIXES:
                pending_gendered[rid] = k  # resolved after first_name gender lands
            elif k in EN_TO_AR_PREFIX:
                resolved_prefix[rid] = EN_TO_AR_PREFIX[k]
            else:
                misses["en2ar"].setdefault(
                    f"__prefix__{k}", (src_prefix, "prefix"))
                resolved_prefix[rid] = None

    # -- chunk misses into batch requests --
    plan = {"model": MODEL_NAME, "chunk_size": args.chunk_size,
             "directions": {}, "resolved_prefix": resolved_prefix,
             "pending_gendered_prefix": pending_gendered}
    n_requests = 0
    for direction, items_by_key in misses.items():
        items = list(items_by_key.items())  # [(norm_key, (src, slot)), ...]
        if not items:
            continue
        chunks = [items[i:i + args.chunk_size]
                   for i in range(0, len(items), args.chunk_size)]
        chunk_records = []
        jsonl_path = f"batch_{direction}.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for ci, chunk in enumerate(chunks):
                request_items = [(i, src, slot)
                                   for i, (k, (src, slot)) in enumerate(chunk)]
                prompt = build_prompt(direction, request_items)
                key = f"{direction}-{ci}"
                f.write(json.dumps({
                    "key": key,
                    "request": {
                        "contents": [{"role": "user",
                                       "parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "thinkingConfig": {"thinkingLevel": "MINIMAL"},
                            "responseMimeType": "application/json",
                            "responseSchema": RESPONSE_SCHEMA,
                            "maxOutputTokens": MAX_OUTPUT_TOKENS,
                        },
                    },
                }, ensure_ascii=False) + "\n")
                chunk_records.append({
                    str(i): {"norm_key": k, "src": src, "slot": slot}
                    for i, (k, (src, slot)) in enumerate(chunk)
                })
                n_requests += 1
        plan["directions"][direction] = {
            "jsonl_path": jsonl_path, "chunks": chunk_records,
        }
        print(f"  {direction}: {len(items)} tokens needing translation -> "
              f"{len(chunks)} request(s) -> {jsonl_path}")

    with open(args.plan, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=0)

    n_prefix_llm = sum(1 for k in misses.get("ar2en", {}) if k.startswith("__prefix__")) \
                    + sum(1 for k in misses.get("en2ar", {}) if k.startswith("__prefix__"))
    n_distinct_name_misses = sum(len(m) for m in misses.values()) - n_prefix_llm
    n_dedup_savings = (total_slots - n_true_cache_hits) - n_distinct_name_misses
    print()
    print(f"{len(rows)} records, {total_slots} name fields")
    print(f"  already resolved by a PRIOR run (real cache hits): {n_true_cache_hits}")
    print(f"  duplicate names within THIS run (dedup, not cache): {n_dedup_savings}")
    print(f"  distinct new names going to the LLM: {n_distinct_name_misses}")
    print(f"  prefixes resolved deterministically: "
          f"{sum(1 for v in resolved_prefix.values() if v is not None)}")
    print(f"  prefixes needing the LLM (new/unknown forms): {n_prefix_llm}")
    print(f"  batch requests to submit: {n_requests}")
    print(f"\nplan written to {args.plan}")
    if n_requests:
        print("next: python translate.py")
    else:
        print("nothing to translate -- everything was already cached. "
              "next: python translate.py  (it will just assemble the CSV)")


if __name__ == "__main__":
    main()
