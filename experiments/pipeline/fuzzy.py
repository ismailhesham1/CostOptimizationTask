# -*- coding: utf-8 -*-
"""DIAGNOSTIC ONLY -- never a substitute for score.py's exact match.

score.py and eval.py both grade with plain string equality after
normalisation; that IS the real metric (see README: "no fuzzy matching...
gold.csv holds exactly one form per field"). What follows here is purely for
understanding WHY a token failed, so you can tell "dropped a hamza" apart
from "produced a completely different name" among tokens that already
failed exact match. Neither classification counts as a pass.
"""
from .common import key as normkey

NEAR_MISS_EDIT_DISTANCE = 1  # <=1 character edit = "near", used only for
                               # triage/prompt-debugging, not for scoring


def levenshtein(a, b):
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


def classify_failures(pool, predictions, results):
    """results: {key: bool} from eval.score_pool. Returns only the FAILED
    keys, each tagged 'near' (<=1 edit) or 'far' (everything else), plus the
    edit distance for context. Exact-match passes are not touched or
    reclassified -- this only explains the failures."""
    out = []
    for k, correct in results.items():
        if correct:
            continue
        v = pool[k]
        gold = normkey(v["gold"])
        pred = normkey(predictions.get(k, ""))
        dist = levenshtein(gold, pred)
        out.append({
            "src": v["src"], "gold": v["gold"], "pred": predictions.get(k, ""),
            "edit_distance": dist,
            "class": "near" if dist <= NEAR_MISS_EDIT_DISTANCE else "far",
        })
    return sorted(out, key=lambda r: r["edit_distance"])


def summarize_failures(failures):
    near = sum(1 for f in failures if f["class"] == "near")
    far = len(failures) - near
    return {"total_failed": len(failures), "near_miss": near, "far_miss": far}
