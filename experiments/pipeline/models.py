# -*- coding: utf-8 -*-
"""The three models under test, and their generation configs.

Picked to bracket the space: a price floor, a modern cheap-tier candidate,
and the quality ceiling (== what Welcome Home runs today, so it doubles as
your baseline measurement).

PRICES BELOW ARE FROM WEB RESEARCH AS OF THIS SESSION, NOT A LIVE API CALL --
re-check https://ai.google.dev/gemini-api/docs/pricing before trusting any
dollar figure this script prints. Standard (non-batch) rate is stored; the
Batch API discount (0.5x) is applied explicitly in cost.py so it stays visible
and easy to correct if Google changes the discount.
"""

MODEL_CONFIGS = {
    "gemini-2.5-flash-lite": {
        "generation_config": {
            "thinkingConfig": {"thinkingBudget": 0},  # fully off
            "responseMimeType": "application/json",
        },
        # $ per 1M tokens, standard (non-batch) rate
        "price_in": 0.10,
        "price_out": 0.40,
        "role": "price floor",
    },
    # Fallback price-floor candidate if 2.5-flash-lite 404s on this key
    # (observed: some accounts get "no longer available to new users" on
    # 2.5-series models regardless of documented retirement date -- run
    # `python -m pipeline.probe_models` first to check). Swap it in via
    # --models if needed.
    "gemini-2.0-flash-lite-001": {
        "generation_config": {
            "responseMimeType": "application/json",
            # 2.0 series predates the thinkingConfig field -- omit it.
        },
        "price_in": 0.075,
        "price_out": 0.30,
        "role": "price floor (fallback)",
    },
    "gemini-3.1-flash-lite": {
        "generation_config": {
            "thinkingConfig": {"thinkingLevel": "MINIMAL"},  # lowest available
            "responseMimeType": "application/json",
        },
        "price_in": 0.25,
        "price_out": 1.50,
        "role": "modern cheap-tier candidate",
    },
    "gemini-2.5-pro": {
        "generation_config": {
            # 2.5-pro has no documented thinkingBudget=0; leave default.
            "responseMimeType": "application/json",
        },
        "price_in": 1.25,   # <=200k token prompts
        "price_out": 10.00,
        # Mandatory baseline model per README ("what Welcome Home runs
        # today"). If this 429s (quota, not 404 -- the model IS reachable,
        # just rate/quota-limited), check
        # https://ai.google.dev/gemini-api/docs/rate-limits and retry the
        # probe on this model alone before assuming it's unusable.
        "role": "quality ceiling / today's baseline model",
    },
    "gemini-3.5-flash-lite": {
        "generation_config": {
            "thinkingConfig": {"thinkingLevel": "MINIMAL"},
            "responseMimeType": "application/json",
        },
        "price_in": 0.30,
        "price_out": 2.50,
        "role": "mid tier (reachable-set bracket)",
    },
    "gemini-3.6-flash": {
        "generation_config": {
            "thinkingConfig": {"thinkingLevel": "MINIMAL"},
            "responseMimeType": "application/json",
        },
        "price_in": 1.50,
        "price_out": 7.50,
        "role": "upper tier (reachable-set bracket)",
    },
}

BATCH_DISCOUNT = 0.5  # Batch API: 50% off standard rate, all models
