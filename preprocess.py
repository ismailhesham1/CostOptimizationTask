#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import json
import os
import re
import unicodedata

import gender_lookup
import gender_classifier

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

# [id, text, gender] triples instead of {"id":.., "text":.., "gender":..}
# objects -- measured 41-63% fewer output tokens across 12 live trials at
# two batch sizes, zero defects, because it doesn't repeat the field names
# as literal tokens for every single item. See EXPERIMENT_LOG.md,
# "Response-format workstream", for the full comparison against TSV
# (rejected: cheaper still, but a real, reproducible, content-triggered
# failure mode with no schema to catch it). Gemini's structured-output
# schema doesn't support fixed-position/heterogeneous tuples, so every
# element is typed as a string -- id comes back as e.g. "0", not 0.
#
# ar2en gets its OWN schema with no gender slot at all (2-element pairs,
# not 3), not just an instruction telling the model to leave it empty --
# AR_TO_EN_PREFIX already disambiguates gender from the Arabic prefix word
# itself, so ar2en never reads this field; there's nothing to structurally
# carry for every single item. See EXPERIMENT_LOG.md, "Gender-inference
# cost-reduction workstream", Task #9.
RESPONSE_SCHEMA_EN2AR = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 3,
                "description": "[id, translated_text, gender] triple",
            },
        },
    },
    "required": ["results"],
}

RESPONSE_SCHEMA_AR2EN = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 2,
                "description": "[id, translated_text] pair",
            },
        },
    },
    "required": ["results"],
}


def response_schema_for(direction):
    return RESPONSE_SCHEMA_EN2AR if direction == "en2ar" else RESPONSE_SCHEMA_AR2EN


def build_prompt(direction, items):
    """items: list of (id, token, slot, known_gender). known_gender is
    None, or an already-resolved 'M'/'F' for en2ar first_name items whose
    gender gender_lookup.py/gender_classifier.py already determined before
    this request was built -- those ids are excluded from the "please
    infer gender" instruction, since the model's answer for them is never
    consumed either way (resolved_prefix is set independently of this
    translation request; see EXPERIMENT_LOG.md Task #10). ar2en never asks
    for gender at all and uses the 2-element RESPONSE_SCHEMA_AR2EN (Task
    #9) -- AR_TO_EN_PREFIX already disambiguates it from the Arabic prefix
    word itself."""
    src_lang = "Arabic" if direction == "ar2en" else "English"
    dst_lang = "English" if direction == "ar2en" else "Arabic"
    lines = [json.dumps([i, tok, slot], ensure_ascii=False)
              for i, tok, slot, _kg in items]

    if direction == "ar2en":
        return (
            STYLE_RULES + "\n"
            f"Translate each of the following {src_lang} name fragments "
            f"into {dst_lang}. Return JSON matching the schema: results is "
            f"an array of [id, translated_text] pairs, one per input, in "
            f"the same order as the input ids below. id must be the same "
            f"value as the input id (as a string).\n\n"
            "Input as [id, text, slot]:\n[\n  " + ",\n  ".join(lines) + "\n]"
        )

    need_gender_ids = [i for i, _tok, slot, kg in items
                         if slot == "first_name" and kg is None]
    if need_gender_ids:
        ids_str = ", ".join(str(i) for i in need_gender_ids)
        gender_instr = (
            f" Infer gender (M/F) only for entries whose id is one of: "
            f"{ids_str}. For every other entry, set gender to an empty "
            f"string."
        )
    else:
        gender_instr = " Set gender to an empty string for every entry."
    return (
        STYLE_RULES + "\n"
        f"Translate each of the following {src_lang} name fragments into "
        f"{dst_lang}. Return JSON matching the schema: results is an array "
        f"of [id, translated_text, gender] triples, one per input, in the "
        f"same order as the input ids below. id must be the same value as "
        f"the input id (as a string).{gender_instr}\n\n"
        "Input as [id, text, slot]:\n[\n  " + ",\n  ".join(lines) + "\n]"
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
    n_gender_pre_resolved = 0  # en2ar first_names sent for translation whose
                                # gender is already known (dict/classifier) --
                                # not asked of the LLM, see build_prompt()
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
            known_gender = None
            if direction == "en2ar" and slot == "first_name":
                # Same two tiers as the prefix-resolution loop below, reused
                # here for a different purpose: if we already know this
                # name's gender, don't spend output tokens asking the LLM
                # to (re-)infer it -- our answer already wins wherever it's
                # actually consumed (resolved_prefix, set independently of
                # this translation request). Safe even for the classifier's
                # ~1.4% error rate: any name it resolves is resolved
                # identically on every future encounter too, so a bad LLM
                # guess cached alongside it would never actually be read.
                g, _conf, _tier = gender_lookup.lookup_gender(src)
                if g is None:
                    g, _clf_conf = gender_classifier.classify_gender(src)
                if g is not None:
                    known_gender = g
                    n_gender_pre_resolved += 1
            misses[direction].setdefault(k, (src, slot, known_gender))

    # -- prefixes: deterministic table first, LLM fallback for the rest --
    resolved_prefix = {}          # record_id -> final prefix string
    pending_gendered = {}         # record_id -> "dr."/"prof."/"eng." (english key)
    n_gender_dict_resolved = 0    # gendered prefixes resolved by gender_lookup.py, $0
    n_gender_clf_resolved = 0     # ...by gender_classifier.py Tier 3 (see that file's
                                   # module docstring for the threshold=0.995 decision
                                   # and its measured ~1.4% wrong-answer rate on the
                                   # subset it fires on -- not a $0-wrong tier like the
                                   # dictionary above it)
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
                    f"__prefix__{k}", (src_prefix, "prefix", None))
                resolved_prefix[rid] = None  # fixed up after translate.py runs
        else:
            k = norm_key(src_prefix)
            if k == "":
                resolved_prefix[rid] = ""
            elif k in GENDERED_PREFIXES:
                # Try the zero-cost static dictionary before falling back to
                # the LLM's inferred gender (see gender_lookup.py). A miss
                # here (None) behaves exactly as before: deferred to
                # translate.py, resolved from the LLM's per-name gender
                # inference once the batch comes back, defaulting to the
                # male form with a warning if that's unresolved too.
                first_name = (row.get("first_name") or "").strip()
                g, _conf, _tier = gender_lookup.lookup_gender(first_name)
                resolved_by = "dict"
                if g is None:
                    # Tier 3: gender_classifier.py, only ever consulted after
                    # the $0-wrong dictionary above has already missed. See
                    # that module's docstring for why threshold=0.995 was
                    # chosen and what it costs in accuracy (measured ~98.6%
                    # on the subset it fires on, not the ~100% the dictionary
                    # and the LLM both measured elsewhere in this project).
                    g, _clf_conf = gender_classifier.classify_gender(first_name)
                    resolved_by = "classifier"
                if g is not None:
                    male, female = EN_TO_AR_PREFIX[k]
                    resolved_prefix[rid] = female if g == "F" else male
                    if resolved_by == "dict":
                        n_gender_dict_resolved += 1
                    else:
                        n_gender_clf_resolved += 1
                else:
                    pending_gendered[rid] = k  # resolved after first_name gender lands
            elif k in EN_TO_AR_PREFIX:
                resolved_prefix[rid] = EN_TO_AR_PREFIX[k]
            else:
                misses["en2ar"].setdefault(
                    f"__prefix__{k}", (src_prefix, "prefix", None))
                resolved_prefix[rid] = None

    # -- chunk misses into batch requests --
    plan = {"model": MODEL_NAME, "chunk_size": args.chunk_size,
             "directions": {}, "resolved_prefix": resolved_prefix,
             "pending_gendered_prefix": pending_gendered}
    n_requests = 0
    for direction, items_by_key in misses.items():
        items = list(items_by_key.items())  # [(norm_key, (src, slot, known_gender)), ...]
        if not items:
            continue
        chunks = [items[i:i + args.chunk_size]
                   for i in range(0, len(items), args.chunk_size)]
        chunk_records = []
        jsonl_path = f"batch_{direction}.jsonl"
        schema = response_schema_for(direction)
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for ci, chunk in enumerate(chunks):
                request_items = [(i, src, slot, kg) for i, (k, (src, slot, kg))
                                   in enumerate(chunk)]
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
                            "responseSchema": schema,
                            "maxOutputTokens": MAX_OUTPUT_TOKENS,
                        },
                    },
                }, ensure_ascii=False) + "\n")
                chunk_records.append({
                    str(i): {"norm_key": k, "src": src, "slot": slot,
                              "known_gender": kg}
                    for i, (k, (src, slot, kg)) in enumerate(chunk)
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
    print(f"    of which, first_names sent for translation WITHOUT asking "
          f"for gender (already known): {n_gender_pre_resolved}")
    print(f"  prefixes resolved deterministically: "
          f"{sum(1 for v in resolved_prefix.values() if v is not None)}")
    print(f"    of which, gendered (dr./prof./eng.) resolved by "
          f"gender_lookup.py (Tier 1/2, $0, ~0% wrong measured): {n_gender_dict_resolved}")
    print(f"    of which, gendered resolved by gender_classifier.py "
          f"(Tier 3, threshold=0.995, ~1.4% wrong measured): {n_gender_clf_resolved}")
    print(f"  gendered prefixes still pending on LLM-inferred gender: "
          f"{len(pending_gendered)}")
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
