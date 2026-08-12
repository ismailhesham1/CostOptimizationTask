# -*- coding: utf-8 -*-
"""Stratified, paired scoring for the bake-off. Uses gold.csv for MEASURING
only -- nothing here feeds back into what the pipeline sends the model.
"""
from collections import Counter

from .common import key as normkey, is_arabic, read_csv

CRITICAL_CHARS = set("أإآةىءؤئ")


def build_token_pool(names_input_path, gold_path):
    """Distinct source tokens -> (gold_answer, direction, slot, frequency,
    is_critical, is_singleton, has_particle). One row per DISTINCT token,
    built once from the full sample -- do not subsample, the critical
    stratum is only ~50 tokens wide and needs every one of them."""
    rows = read_csv(names_input_path)
    gold = {r["record_id"]: r for r in read_csv(gold_path)}

    freq = Counter()
    pool = {}
    for row in rows:
        g = gold[row["record_id"]]
        for slot in ("first_name", "last_name"):
            src = (row.get(slot) or "").strip()
            if not src:
                continue
            tgt = (g.get(slot) or "").strip()
            k = normkey(src)
            freq[k] += 1
            direction = "ar2en" if is_arabic(src) else "en2ar"
            critical = is_arabic(tgt) and any(c in tgt for c in CRITICAL_CHARS)
            particle = (" " in src.strip()
                        or src.lower().startswith("al-")
                        or normkey(src).startswith("ال"))
            pool[k] = {
                "src": src, "gold": tgt, "direction": direction,
                "slot": slot, "critical": critical, "particle": particle,
            }
    for k, v in pool.items():
        v["freq"] = freq[k]
        v["singleton"] = freq[k] == 1
    return pool


def score_pool(pool, predictions):
    """predictions: {normkey(src): predicted_text}. Returns overall +
    per-stratum accuracy, and the list of (key, correct) for McNemar."""
    strata = {
        "overall": lambda v: True,
        "ar2en": lambda v: v["direction"] == "ar2en",
        "en2ar": lambda v: v["direction"] == "en2ar",
        "en2ar_critical": lambda v: v["direction"] == "en2ar" and v["critical"],
        "particle": lambda v: v["particle"],
        "singleton": lambda v: v["singleton"],
    }
    results = {k: normkey(v["gold"]) == normkey(predictions.get(k, ""))
               for k, v in pool.items()}
    report = {}
    for name, pred in strata.items():
        keys = [k for k, v in pool.items() if pred(v)]
        n = len(keys)
        hits = sum(results[k] for k in keys)
        report[name] = {"n": n, "hits": hits,
                         "accuracy": hits / n if n else float("nan")}
    return report, results


def mcnemar(results_a, results_b):
    """Paired comparison on shared keys: counts where the two models
    disagree. More sensitive than comparing marginal accuracy when n per
    stratum is small (as it is here for the critical stratum)."""
    keys = set(results_a) & set(results_b)
    a_only = sum(results_a[k] and not results_b[k] for k in keys)
    b_only = sum(results_b[k] and not results_a[k] for k in keys)
    both = sum(results_a[k] and results_b[k] for k in keys)
    neither = sum(not results_a[k] and not results_b[k] for k in keys)
    return {"a_right_b_wrong": a_only, "b_right_a_wrong": b_only,
            "both_right": both, "both_wrong": neither, "n": len(keys)}
