# -*- coding: utf-8 -*-
"""Cheap sanity check: which candidate models can this API key actually call?

Model availability has been observed to vary per-account independently of
what client.models.list() shows and independently of documented retirement
dates (some 2.5-series models 404 as "no longer available to new users" on
freshly-provisioned keys, even for plain generate_content -- see
https://discuss.ai.google.dev/t/gemini-2-5-pro-returns-no-longer-available-to-new-users).

Run this BEFORE submitting batch jobs. One tiny synchronous call per model,
max_output_tokens capped, effectively free.

    python -m pipeline.probe_models
"""
import os

CANDIDATES = [
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite-001",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro",          # mandatory baseline model per README -- if
                                 # this fails, the baseline needs a fallback
                                 # plan, flag it and stop rather than guess.
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
]


def main():
    from google import genai
    from google.genai import types

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set.")
    client = genai.Client(api_key=key)

    print(f"probing {len(CANDIDATES)} models with a 1-token call each...\n")
    ok, failed = [], []
    for name in CANDIDATES:
        try:
            resp = client.models.generate_content(
                model=name,
                contents="Say OK.",
                config=types.GenerateContentConfig(max_output_tokens=5),
            )
            print(f"  OK    {name}")
            ok.append(name)
        except Exception as e:  # noqa: BLE001 -- deliberately broad, reported
            msg = str(e).splitlines()[0][:500]
            print(f"  FAIL  {name}  -- {msg}")
            failed.append(name)

    print(f"\n{len(ok)} available, {len(failed)} unavailable on this key.")
    if "gemini-2.5-pro" in failed:
        print(
            "\n!! gemini-2.5-pro failed -- this is the mandatory baseline "
            "model per the README. You cannot measure 'what Welcome Home "
            "runs today' with this key as-is. Options: request access/quota "
            "for this project, or measure the baseline on whichever "
            "model *is* available and say so explicitly in SUBMISSION.md "
            "(this is exactly the kind of thing rule 2 wants logged)."
        )


if __name__ == "__main__":
    main()
