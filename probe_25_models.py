#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Checks whether the three gemini-2.5 models are reachable via sync
(generate_content) on the current GEMINI_API_KEY. One tiny 1-token call
per model -- effectively free.

Why this exists: earlier keys hit a hard 404 ("no longer available to new
users") on gemini-2.5-flash-lite and a 429 with limit:0 on gemini-2.5-pro,
both via this same sync endpoint -- not a batch-specific issue. Worth
re-checking on a new key since gemini-2.5-flash DID work via sync on the
most recent key, unlike earlier ones.

Usage:
    python probe_25_models.py
"""
import os

MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]


def main():
    from google import genai
    from google.genai import types

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set.")
    client = genai.Client(api_key=key)

    print("testing the three gemini-2.5 models via sync (generate_content)...\n")
    results = {}
    for name in MODELS:
        try:
            client.models.generate_content(
                model=name, contents="Say OK.",
                config=types.GenerateContentConfig(max_output_tokens=5),
            )
            print(f"  OK    {name}")
            results[name] = True
        except Exception as e:  # noqa: BLE001 -- deliberately broad, reported
            print(f"  FAIL  {name}")
            print(f"        {str(e)[:400]}")
            results[name] = False

    print()
    ok = [n for n, v in results.items() if v]
    if ok:
        print(f"usable via sync: {', '.join(ok)}")
    else:
        print("none of the three 2.5 models are usable via sync on this key.")


if __name__ == "__main__":
    main()
