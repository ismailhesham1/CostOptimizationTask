# -*- coding: utf-8 -*-
"""Persistent bidirectional name cache. Plain Python + JSON, no database.

Every resolved token is stored under BOTH its own key and its counterpart's
key, because the token map is a verified bijection (see analysis notes):
every source token maps to exactly one target token and vice versa. So one
API answer resolves two future lookups, in either direction.

Gender is stored separately, keyed by the CASEFOLDED FIRST NAME (either
script), because gender is a property of the person, not of one field.
"""
import json
import os

from .common import key as normkey


class NameCache:
    def __init__(self, path="cache.json"):
        self.path = path
        self.names = {}    # normalised source token -> exact target string
        self.gender = {}   # normalised first-name token -> "M" | "F"
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.names = data.get("names", {})
            self.gender = data.get("gender", {})

    def get(self, token):
        return self.names.get(normkey(token))

    def get_gender(self, first_name_token):
        return self.gender.get(normkey(first_name_token))

    def put(self, src, dst, gender=None):
        """Record a resolved pair. Stores both lookup directions."""
        if not src or not dst:
            return
        self.names[normkey(src)] = dst
        self.names[normkey(dst)] = src
        if gender:
            self.gender[normkey(src)] = gender
            self.gender[normkey(dst)] = gender

    def __contains__(self, token):
        return normkey(token) in self.names

    def __len__(self):
        return len(self.names)

    def save(self):
        """Atomic write: never leaves a half-written cache on disk."""
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"names": self.names, "gender": self.gender},
                f, ensure_ascii=False, indent=0,
            )
        os.replace(tmp, self.path)
