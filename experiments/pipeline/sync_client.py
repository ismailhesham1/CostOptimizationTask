# -*- coding: utf-8 -*-
"""Synchronous fallback: same prompts, same scoring, no Batch API.

Use this when batches.create is denied at the project level (seen: uniform
403 PERMISSION_DENIED across every model -- a project/billing gate, not a
per-model or code issue). Real usage_metadata is still captured; cost is
reported at the STANDARD rate. The 50% batch discount is layered back in
afterwards as an explicit, documented projection once batch access clears --
never silently assumed.
"""
import json

from .models import MODEL_CONFIGS
from .prompts import RESPONSE_SCHEMA


def run_sync_chunk(client, model_name, prompt):
    """One synchronous generate_content call for one chunk's prompt.
    Returns (parsed_json_dict, usage_dict) in the same shape download_results()
    produces, so downstream scoring/cost code doesn't need to know which
    mode produced the data."""
    cfg = MODEL_CONFIGS[model_name]
    config = dict(cfg["generation_config"])
    config["responseSchema"] = RESPONSE_SCHEMA

    resp = client.models.generate_content(
        model=model_name, contents=prompt, config=config,
    )
    usage = resp.usage_metadata
    usage_dict = {
        "prompt_tokens": getattr(usage, "prompt_token_count", 0) or 0,
        "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
        "thinking_tokens": getattr(usage, "thoughts_token_count", 0) or 0,
        "total_tokens": getattr(usage, "total_token_count", 0) or 0,
    }
    parsed = json.loads(resp.text)
    return parsed, usage_dict
