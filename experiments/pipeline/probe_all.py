# -*- coding: utf-8 -*-
"""List every text-generation model this key can actually call -- not just
what's in the catalog (client.models.list() shows models regardless of
whether YOU can reach them, as we've seen repeatedly: listed != callable).

Filters the full catalog down to models that declare generateContent
support, then does one tiny real call per model to confirm access.

    python -m pipeline.probe_all
"""
import os


def main():
    from google import genai
    from google.genai import types

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set.")
    client = genai.Client(api_key=key)

    catalog = list(client.models.list())
    candidates = []
    for m in catalog:
        actions = getattr(m, "supported_actions", None) or []
        if actions and "generateContent" not in actions:
            continue  # explicitly doesn't support it -- skip (tts/embedding/etc.)
        name = m.name.replace("models/", "")
        candidates.append(name)

    print(f"{len(catalog)} models in catalog, {len(candidates)} declare "
          f"generateContent support. Testing each with a 1-token call...\n")

    usable = []
    for name in candidates:
        try:
            client.models.generate_content(
                model=name, contents="Say OK.",
                config=types.GenerateContentConfig(max_output_tokens=5),
            )
            print(f"  OK    {name}")
            usable.append(name)
        except Exception as e:  # noqa: BLE001 -- deliberately broad, reported
            print(f"  FAIL  {name}  -- {str(e).splitlines()[0][:150]}")

    print(f"\n{len(usable)}/{len(candidates)} usable on this key:")
    for name in usable:
        print(f"  {name}")


if __name__ == "__main__":
    main()
