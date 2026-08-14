#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 5 of the gender-inference workstream (EXPERIMENT_LOG.md): a
statistical classifier, tried explicitly as an experiment to be measured
and then kept or discarded on evidence -- not assumed to be an improvement.

Character n-gram Naive Bayes, pure Python (no new dependency -- this
project's existing convention, see score.py's "no third-party packages").
Trained on gender_lookup.py's GENDER_TABLE (584 hand-curated names) as the
only labelled data available in this repo. That is a real constraint on
what this experiment can prove, stated up front rather than after the
result: cross-validation below measures how well surname-final letter
patterns predict gender *within the same population the dictionary was
curated from*, not against an independent corpus.

Why try this at all, given the dictionary already exists: the dictionary
only fires on an exact match. This classifier's only possible contribution
is on names that AREN'T in the dictionary at all -- both the explicit
AMBIGUOUS bucket and any genuinely novel name at production scale. Whether
it's safe to trust there is exactly what this file's __main__ block
measures.

THRESHOLD DECISION (EXPERIMENT_LOG.md, Phase 5, extended sweep): a pooled
40-draw sweep found accuracy climbs with the threshold -- 83.7% @0.90,
88.6% @0.95, 95.7% @0.99, 98.6% @0.995, 100.0% (0/311) @0.999 -- but
coverage on the actual target population (names the static dictionary
misses, e.g. River/Sage/Sky/Justice/Liberty) collapses even faster: none
of the 10 real ambiguous names in this project's sample clear 0.999, or
even 0.995. AUTO_RESOLVE_THRESHOLD = 0.995 is set here on an explicit
decision to accept a measured ~1.4% wrong-answer rate on whatever slice of
names it does resolve, in exchange for some real coverage rather than the
0.999 point's ~0% real-world coverage. This is a deliberate departure from
this workstream's earlier zero-tolerance stance (the dictionary and the
LLM both measured effectively 0 wrong) -- flagged plainly, not hidden,
because it changes what "safe" means for names this tier touches. See
EXPERIMENT_LOG.md for the full sweep and the tradeoff as stated before this
threshold was chosen.
"""
import random

from gender_lookup import GENDER_TABLE, norm_key

AUTO_RESOLVE_THRESHOLD = 0.995


ALL_FEATURE_TYPES = ("last1", "last2", "last3", "first1", "first2")


def _features(name, feature_types=ALL_FEATURE_TYPES):
    n = norm_key(name)
    candidates = {
        "last1": n[-1:],
        "last2": n[-2:] if len(n) >= 2 else n,
        "last3": n[-3:] if len(n) >= 3 else n,
        "first1": n[:1],
        "first2": n[:2] if len(n) >= 2 else n,
    }
    return {(t, candidates[t]) for t in feature_types}


class NaiveBayesGenderModel:
    """Fit on an iterable of (name, gender) pairs where gender in {'M','F'}."""

    def __init__(self, feature_types=ALL_FEATURE_TYPES):
        self.feature_types = feature_types
        self.counts = {}      # (feat_type, feat_value) -> {'M': n, 'F': n}
        self.vocab_size = {}  # feat_type -> distinct value count seen in training
        self.class_totals = {"M": 0, "F": 0}

    def fit(self, examples):
        vocab = {}
        for name, gender in examples:
            self.class_totals[gender] += 1
            for feat in _features(name, self.feature_types):
                feat_type, _ = feat
                vocab.setdefault(feat_type, set()).add(feat)
                bucket = self.counts.setdefault(feat, {"M": 0, "F": 0})
                bucket[gender] += 1
        self.vocab_size = {t: len(v) for t, v in vocab.items()}
        return self

    def _feature_log_prob(self, feat, gender):
        feat_type, _ = feat
        v = self.vocab_size.get(feat_type, 1)
        bucket = self.counts.get(feat, {"M": 0, "F": 0})
        total = self.class_totals[gender]
        # Laplace smoothing -- an unseen feature value contributes a small,
        # equal amount of evidence to both classes, not zero/undefined.
        return _log((bucket[gender] + 1) / (total + v))

    def predict(self, name):
        """Returns (gender, confidence) where confidence = P(predicted)."""
        total_m, total_f = self.class_totals["M"], self.class_totals["F"]
        n = total_m + total_f
        if n == 0:
            return None, 0.0
        score_m = _log(total_m / n)
        score_f = _log(total_f / n)
        for feat in _features(name, self.feature_types):
            score_m += self._feature_log_prob(feat, "M")
            score_f += self._feature_log_prob(feat, "F")
        # softmax over the two log-scores
        m = max(score_m, score_f)
        p_m = _exp(score_m - m)
        p_f = _exp(score_f - m)
        z = p_m + p_f
        p_m, p_f = p_m / z, p_f / z
        return ("M", p_m) if p_m >= p_f else ("F", p_f)


def _log(x):
    import math
    return math.log(x)


def _exp(x):
    import math
    return math.exp(x)


def _examples(tier_filter=None):
    out = []
    for name, (g, _conf, tier) in GENDER_TABLE.items():
        if tier_filter is not None and tier != tier_filter:
            continue
        out.append((name, g))
    return out


_production_model = None  # lazy singleton, trained once on first use


def classify_gender(name, threshold=AUTO_RESOLVE_THRESHOLD):
    """Production entry point for preprocess.py's Tier 3: trained once on
    the full gender_lookup.py dictionary, applied only when Tiers 1-2
    (gender_lookup.lookup_gender) have already missed. Returns (gender,
    confidence) if confidence >= threshold, else (None, confidence) -- a
    miss, to be treated exactly like a dictionary miss by the caller (fall
    through to the LLM's inferred gender, same as always)."""
    global _production_model
    if _production_model is None:
        _production_model = NaiveBayesGenderModel().fit(_examples())
    pred, conf = _production_model.predict(name)
    return (pred, conf) if conf >= threshold else (None, conf)


def cross_validate(k=5, seed=42, feature_types=ALL_FEATURE_TYPES,
                    threshold=AUTO_RESOLVE_THRESHOLD, examples=None,
                    collect_predictions=False):
    """One k-fold CV pass. Returns accuracy/coverage at `threshold`, plus
    (name, true_gender, predicted, confidence) tuples if collect_predictions."""
    examples = list(examples if examples is not None else _examples())
    rng = random.Random(seed)
    rng.shuffle(examples)
    folds = [examples[i::k] for i in range(k)]

    raw_correct = raw_total = 0
    gated_correct = gated_total = 0
    predictions = []
    for i in range(k):
        test = folds[i]
        train = [ex for j, f in enumerate(folds) if j != i for ex in f]
        model = NaiveBayesGenderModel(feature_types).fit(train)
        for name, true_gender in test:
            pred, conf = model.predict(name)
            raw_total += 1
            if pred == true_gender:
                raw_correct += 1
            if conf >= threshold:
                gated_total += 1
                if pred == true_gender:
                    gated_correct += 1
            if collect_predictions:
                predictions.append((name, true_gender, pred, conf))
    result = {
        "n": len(examples),
        "raw_accuracy": raw_correct / raw_total,
        "gated_accuracy": (gated_correct / gated_total) if gated_total else None,
        "gated_coverage": gated_total / raw_total,
    }
    if collect_predictions:
        result["predictions"] = predictions
    return result


def repeated_cross_validate(k=5, n_repeats=20, feature_types=ALL_FEATURE_TYPES,
                             threshold=AUTO_RESOLVE_THRESHOLD):
    """Addresses the single-draw weakness this project has already flagged
    elsewhere for exactly this kind of measurement (see EXPERIMENT_LOG.md,
    the chunk-size sweep, §6 #15 in SUBMISSION.md): one CV split is one
    sample from a noisy process, not a stable estimate. Runs n_repeats
    independent 5-fold splits (different seeds) and reports mean +/- stdev."""
    raw_accs, gated_accs, coverages = [], [], []
    for seed in range(n_repeats):
        r = cross_validate(k=k, seed=seed, feature_types=feature_types,
                            threshold=threshold)
        raw_accs.append(r["raw_accuracy"])
        coverages.append(r["gated_coverage"])
        if r["gated_accuracy"] is not None:
            gated_accs.append(r["gated_accuracy"])
    return {
        "n_repeats": n_repeats,
        "raw_mean": _mean(raw_accs), "raw_std": _std(raw_accs),
        "gated_mean": _mean(gated_accs), "gated_std": _std(gated_accs),
        "coverage_mean": _mean(coverages), "coverage_std": _std(coverages),
        "gated_runs": len(gated_accs),
    }


def pooled_threshold_sweep(thresholds, k=5, n_repeats=40, examples=None):
    """More stable than averaging per-draw ratios (repeated_cross_validate)
    at extreme thresholds, where a single fold may have only a handful of
    predictions above the bar -- pools every prediction from every draw
    first, THEN computes accuracy/coverage per threshold from the pooled
    set. Also reports n_confident so a near-empty bucket is visible instead
    of hiding behind a percentage."""
    all_preds = []  # (true_gender, predicted, confidence)
    for seed in range(n_repeats):
        r = cross_validate(k=k, seed=seed, examples=examples,
                            collect_predictions=True)
        all_preds.extend((t, p, c) for _, t, p, c in r["predictions"])
    total = len(all_preds)

    rows = []
    for t in thresholds:
        bucket = [(true, pred) for true, pred, conf in all_preds if conf >= t]
        n = len(bucket)
        acc = (sum(1 for true, pred in bucket if true == pred) / n) if n else None
        rows.append({"threshold": t, "n_confident": n, "n_total": total,
                      "coverage": n / total, "accuracy": acc})
    return rows


def threshold_sweep(thresholds=(0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 0.99),
                     n_repeats=10):
    """Accuracy/coverage tradeoff at each threshold, averaged over
    n_repeats CV draws per threshold (same repeated-draw discipline as
    repeated_cross_validate)."""
    rows = []
    for t in thresholds:
        r = repeated_cross_validate(n_repeats=n_repeats, threshold=t)
        rows.append((t, r["coverage_mean"], r["gated_mean"], r["gated_std"]))
    return rows


def feature_ablation(n_repeats=10):
    """Does the full 5-feature set actually beat simpler feature sets, or
    is it overfitting sparse n-gram counts on only 584 examples? Classic
    name-gender baselines (e.g. the standard NLTK tutorial) use last-letter
    alone -- worth checking whether more features actually help here."""
    variants = {
        "last1 only (classic baseline)": ("last1",),
        "last1+last2": ("last1", "last2"),
        "last1+last2+last3": ("last1", "last2", "last3"),
        "first1+first2 only": ("first1", "first2"),
        "all 5 (shipped)": ALL_FEATURE_TYPES,
    }
    rows = []
    for label, feats in variants.items():
        r = repeated_cross_validate(n_repeats=n_repeats, feature_types=feats)
        rows.append((label, r["raw_mean"], r["raw_std"],
                      r["gated_mean"], r["gated_std"], r["coverage_mean"]))
    return rows


def tier_breakdown(n_repeats=10):
    """Cross-validated separately within tier1 (Arabic given names) and
    tier2 (Western given names) -- do NOT train on one tier and test on the
    other (that answers a different, less relevant question); this answers
    whether accuracy differs by name origin when both train and test stay
    within the same population."""
    rows = []
    for tier in ("tier1_arabic", "tier2_western"):
        ex = _examples(tier_filter=tier)
        raw_accs = []
        for seed in range(n_repeats):
            r = cross_validate(k=5, seed=seed, examples=ex)
            raw_accs.append(r["raw_accuracy"])
        rows.append((tier, len(ex), _mean(raw_accs), _std(raw_accs)))
    return rows


def calibration_report(n_repeats=10, bins=(0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.01)):
    """Is confidence trustworthy, i.e. is a 90%-confidence prediction right
    about 90% of the time? Naive Bayes is well known to be overconfident
    (the independence assumption double-counts correlated features like
    last1/last2/last3 all pointing the same way) -- this checks whether
    that's actually happening here, rather than assuming AUTO_RESOLVE_
    THRESHOLD=0.90 means what it sounds like it means."""
    all_preds = []
    for seed in range(n_repeats):
        r = cross_validate(k=5, seed=seed, collect_predictions=True)
        all_preds.extend(r["predictions"])
    rows = []
    for lo, hi in zip(bins, bins[1:]):
        bucket = [(t, p) for _, t, p, c in all_preds if lo <= c < hi]
        if not bucket:
            continue
        correct = sum(1 for t, p in bucket if t == p)
        rows.append((lo, hi, len(bucket), correct / len(bucket)))
    return rows


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


if __name__ == "__main__":
    print("=" * 72)
    print("EXTENDED THRESHOLD SWEEP -- pooled over 40 CV draws (2920 predictions")
    print("per threshold from the full population), searching for a threshold")
    print("reliable enough to auto-resolve without a measurable quality hit.")
    print("=" * 72)
    thresholds = (0.90, 0.95, 0.99, 0.995, 0.999, 0.9999, 0.99999)
    rows = pooled_threshold_sweep(thresholds, n_repeats=40)
    print(f"  {'threshold':<10} {'n_confident':>12} {'coverage':>10} {'accuracy':>10}")
    for r in rows:
        acc_str = f"{r['accuracy']:.2%}" if r["accuracy"] is not None else "n/a (0 confident)"
        print(f"  {r['threshold']:<10} {r['n_confident']:>12} "
              f"{r['coverage']:>9.2%} {acc_str:>10}")

    print()
    print("=" * 72)
    print("Same sweep, restricted to tier1_arabic only (where the earlier")
    print("tier breakdown found the strongest signal)")
    print("=" * 72)
    ex_tier1 = _examples(tier_filter="tier1_arabic")
    rows = pooled_threshold_sweep(thresholds, n_repeats=40, examples=ex_tier1)
    print(f"  {'threshold':<10} {'n_confident':>12} {'coverage':>10} {'accuracy':>10}")
    for r in rows:
        acc_str = f"{r['accuracy']:.2%}" if r["accuracy"] is not None else "n/a (0 confident)"
        print(f"  {r['threshold']:<10} {r['n_confident']:>12} "
              f"{r['coverage']:>9.2%} {acc_str:>10}")
