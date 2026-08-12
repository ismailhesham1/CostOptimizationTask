# -*- coding: utf-8 -*-
"""Bare minimum check: does GEMINI_API_KEY authenticate at all?

Tests auth only -- not any particular model's availability (that's
probe_models.py for sync access, probe_batch.py for the real batch
codepath). Run this first; if it fails, there's no point running the
others.

    python -m pipeline.probe_key
"""
import os


def main():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("FAIL  GEMINI_API_KEY is not set in this shell.")
        print('      PowerShell: $env:GEMINI_API_KEY = "your-key-here"')
        raise SystemExit(1)

    masked = key[:4] + "..." + key[-4:] if len(key) > 8 else "(short key)"
    print(f"GEMINI_API_KEY is set ({masked}), checking it authenticates...")

    try:
        from google import genai
    except ImportError:
        print("FAIL  google-genai is not installed. Run: pip install -r requirements.txt")
        raise SystemExit(1)

    try:
        client = genai.Client(api_key=key)
        # Listing models requires only a valid, authenticated key -- no
        # per-model access or quota needed, so this isolates auth failures
        # from the 404/429 access issues the other probes catch.
        models = list(client.models.list())
    except Exception as e:  # noqa: BLE001 -- deliberately broad, reported
        print(f"FAIL  key did not authenticate -- {str(e).splitlines()[0][:500]}")
        raise SystemExit(1)

    print(f"OK    key is valid, {len(models)} models visible to this project.")
    print("      Next: python -m pipeline.probe_batch")


if __name__ == "__main__":
    main()
