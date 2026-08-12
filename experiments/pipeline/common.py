# -*- coding: utf-8 -*-
"""Shared helpers: normalisation, script detection, particle handling.

Import rule for this whole package: normalise the CACHE KEY aggressively
(casefold, whitespace-collapse). Never normalise a VALUE or a model OUTPUT —
Arabic orthographic marks (hamza, ta marbuta, alif maqsura) distinguish real
names from each other and must be preserved verbatim.
"""
import csv
import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


def key(s):
    """The one normalisation used for cache/dedup keys. Lossless for identity."""
    text = unicodedata.normalize("NFC", s or "")
    return _WHITESPACE.sub(" ", text).strip().casefold()


def is_arabic(s):
    """True if the string contains any Arabic-script character."""
    return any("؀" <= c <= "ۿ" for c in (s or ""))


def direction_of(token):
    """'ar2en' or 'en2ar' based on script of the source token."""
    return "ar2en" if is_arabic(token) else "en2ar"


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
