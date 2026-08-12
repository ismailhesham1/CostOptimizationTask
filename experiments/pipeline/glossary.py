# -*- coding: utf-8 -*-
"""House-style glossary, built ONLY from names_input.csv (never gold.csv).

Because sign-ups arrive in both languages, the correct target-language
spelling for a slice of tokens is often already sitting somewhere else in
the input file (e.g. record R014 submits 'Mohammed' in English while R512
submits 'محمد' in Arabic — same person-name, no pairing needed, just two
independent appearances). Handing the model both vocabularies as "known
accepted forms" converts some coin-flip transliterations (Mohammed vs
Muhammad vs Mohamad) into exact matches, at zero extra API cost.

This is legitimate under the task rules: it is derived from input data the
production pipeline will always have, not from the held-out answer key.
"""
from .common import read_csv, is_arabic, key as normkey

FIELDS = ("prefix", "first_name", "last_name")


def build_glossaries(names_input_path):
    """Returns (english_terms, arabic_terms): sorted lists of distinct,
    exact-as-submitted tokens seen anywhere in the input file."""
    rows = read_csv(names_input_path)
    en, ar = {}, {}  # normkey -> first exact form seen, to dedupe casing
    for row in rows:
        for field in FIELDS:
            val = (row.get(field) or "").strip()
            if not val:
                continue
            bucket = ar if is_arabic(val) else en
            bucket.setdefault(normkey(val), val)
    return sorted(en.values()), sorted(ar.values())


def glossary_block(terms, limit=800):
    """Render a glossary list for prompt injection, capped to keep requests
    small. If your production vocabulary grows past `limit`, keep only the
    most frequent terms (track frequency in the cache) rather than truncating
    arbitrarily."""
    shown = terms[:limit]
    return ", ".join(shown)
