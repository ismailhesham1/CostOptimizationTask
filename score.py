#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Score a translated name file against data/gold.csv.

Usage:
    python3 score.py my_output.csv
    python3 score.py my_output.csv --gold data/gold.csv --failures failures.csv

Your file must be UTF-8 CSV with a header row containing at least these
columns (extra columns are ignored, column order does not matter):

    record_id, prefix, first_name, last_name

...where prefix / first_name / last_name hold the TARGET-language values
for that record. Records whose gold prefix is empty must have an empty
prefix in your file.

HOW A FIELD IS COMPARED
-----------------------
Before comparing, both sides get exactly these four transformations and
nothing else:

    1. Unicode NFC normalisation
    2. leading / trailing whitespace stripped
    3. runs of internal whitespace collapsed to a single space
    4. casefold (so capitalisation never matters)

The comparison is then a plain string equality check. There is no fuzzy
matching, no per-character scoring, and no list of alternative accepted
spellings: gold holds exactly one form per field.

Requires Python 3.8+. No third-party packages.
"""

import argparse
import csv
import re
import sys
import unicodedata
from collections import Counter

FIELDS = ("prefix", "first_name", "last_name")
REQUIRED_COLUMNS = ("record_id",) + FIELDS
_WHITESPACE = re.compile(r"\s+")


def normalise(value):
    """The one and only normalisation applied before comparison."""
    text = unicodedata.normalize("NFC", value or "")
    return _WHITESPACE.sub(" ", text).strip().casefold()


def read_csv(path, label):
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                sys.exit(f"error: {label} file '{path}' is empty")
            missing = [c for c in REQUIRED_COLUMNS
                       if c not in reader.fieldnames]
            if missing:
                sys.exit(
                    f"error: {label} file '{path}' is missing required "
                    f"column(s): {', '.join(missing)}\n"
                    f"       found: {', '.join(reader.fieldnames)}"
                )
            return [dict(row) for row in reader]
    except FileNotFoundError:
        sys.exit(f"error: {label} file '{path}' not found")
    except UnicodeDecodeError:
        sys.exit(f"error: {label} file '{path}' is not valid UTF-8")


def index_by_id(rows, path):
    indexed = {}
    duplicates = Counter()
    for row in rows:
        rid = (row.get("record_id") or "").strip()
        if not rid:
            continue
        if rid in indexed:
            duplicates[rid] += 1
        indexed[rid] = row
    if duplicates:
        shown = ", ".join(sorted(duplicates)[:5])
        sys.exit(
            f"error: '{path}' contains duplicate record_id values "
            f"({len(duplicates)} affected, e.g. {shown}). "
            f"Emit exactly one row per record_id."
        )
    return indexed


def bar(fraction, width=32):
    filled = int(round(fraction * width))
    return "#" * filled + "." * (width - filled)


def main():
    parser = argparse.ArgumentParser(
        description="Score translated names against the gold file.")
    parser.add_argument("submission",
                        help="your CSV of translated names")
    parser.add_argument("--gold", default="data/gold.csv",
                        help="gold file (default: data/gold.csv)")
    parser.add_argument("--failures", default="failures.csv",
                        help="where to write the failure report "
                             "(default: failures.csv)")
    args = parser.parse_args()

    gold_rows = read_csv(args.gold, "gold")
    sub_rows = read_csv(args.submission, "submission")
    gold = index_by_id(gold_rows, args.gold)
    sub = index_by_id(sub_rows, args.submission)

    total = len(gold)
    answered = 0
    missing_ids = []
    unknown_ids = sorted(set(sub) - set(gold))
    field_hits = Counter()
    record_hits = 0
    failures = []

    for rid in sorted(gold):
        gold_row = gold[rid]
        sub_row = sub.get(rid)
        if sub_row is None:
            missing_ids.append(rid)
            for field in FIELDS:
                failures.append({
                    "record_id": rid,
                    "field": field,
                    "expected": gold_row.get(field, ""),
                    "got": "",
                    "reason": "missing_record",
                })
            continue

        answered += 1
        all_match = True
        for field in FIELDS:
            expected = gold_row.get(field, "")
            got = sub_row.get(field, "")
            if normalise(expected) == normalise(got):
                field_hits[field] += 1
            else:
                all_match = False
                failures.append({
                    "record_id": rid,
                    "field": field,
                    "expected": expected,
                    "got": got,
                    "reason": "mismatch",
                })
        if all_match:
            record_hits += 1

    with open(args.failures, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["record_id", "field", "expected", "got", "reason"])
        writer.writeheader()
        writer.writerows(failures)

    pct = (lambda n: n / total if total else 0.0)

    print()
    print("=" * 60)
    print(f"  submission : {args.submission}")
    print(f"  gold       : {args.gold}")
    print("=" * 60)
    print(f"  gold records            {total}")
    print(f"  records you answered    {answered}")
    if missing_ids:
        print(f"  records you skipped     {len(missing_ids)}"
              f"   (e.g. {', '.join(missing_ids[:5])})")
    if unknown_ids:
        print(f"  unknown record_ids      {len(unknown_ids)}"
              f"   (ignored, e.g. {', '.join(unknown_ids[:5])})")
    print("-" * 60)
    for field in FIELDS:
        frac = pct(field_hits[field])
        print(f"  {field:<12} {frac:7.2%}  {bar(frac)}")
    frac = pct(record_hits)
    print("-" * 60)
    print(f"  {'FULL RECORD':<12} {frac:7.2%}  {bar(frac)}"
          f"   ({record_hits}/{total})")
    print("=" * 60)
    print(f"  {len(failures)} failing field(s) written to {args.failures}")
    print()


if __name__ == "__main__":
    main()
