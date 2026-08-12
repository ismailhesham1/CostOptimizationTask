# -*- coding: utf-8 -*-
"""Turns real usage_metadata into dollars. Never estimate -- measure."""
from .models import MODEL_CONFIGS, BATCH_DISCOUNT


def request_cost(model_name, usage, batch=True):
    cfg = MODEL_CONFIGS[model_name]
    discount = BATCH_DISCOUNT if batch else 1.0
    in_cost = usage["prompt_tokens"] / 1e6 * cfg["price_in"] * discount
    # thinking tokens bill at the output rate
    out_cost = ((usage["output_tokens"] + usage.get("thinking_tokens", 0))
                / 1e6 * cfg["price_out"] * discount)
    return in_cost + out_cost


def summarize(model_name, usages, batch=True):
    total = sum(request_cost(model_name, u, batch) for u in usages)
    tok_in = sum(u["prompt_tokens"] for u in usages)
    tok_out = sum(u["output_tokens"] for u in usages)
    tok_think = sum(u.get("thinking_tokens", 0) for u in usages)
    return {
        "model": model_name,
        "requests": len(usages),
        "tokens_in": tok_in,
        "tokens_out": tok_out,
        "tokens_thinking": tok_think,
        "cost_usd": round(total, 6),
    }
