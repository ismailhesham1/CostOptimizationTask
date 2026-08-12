# -*- coding: utf-8 -*-
"""Quick single-model check: does this key work with gemini-2.5-flash,
both synchronously and via the Batch API.

    python -m pipeline.probe_flash
"""
import json
import os
import tempfile

MODEL = "gemini-2.5-flash"


def main():
    from google import genai
    from google.genai import types

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set.")
    client = genai.Client(api_key=key)

    print(f"testing {MODEL} ...\n")

    # -- sync --
    try:
        client.models.generate_content(
            model=MODEL, contents="Say OK.",
            config=types.GenerateContentConfig(max_output_tokens=5),
        )
        print("  sync   OK")
    except Exception as e:  # noqa: BLE001 -- deliberately broad, reported
        print(f"  sync   FAIL -- {str(e).splitlines()[0][:300]}")

    # -- batch --
    tmp_dir = tempfile.mkdtemp(prefix="probe_flash_")
    path = os.path.join(tmp_dir, "probe.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "key": "probe-0",
            "request": {"contents": [{"role": "user",
                                       "parts": [{"text": "Say OK."}]}]},
        }) + "\n")
    try:
        uploaded = client.files.upload(
            file=path, config=types.UploadFileConfig(mime_type="application/jsonl"))
        job = client.batches.create(
            model=MODEL, src=uploaded.name,
            config={"display_name": "probe-flash"})
        print(f"  batch  OK (job: {job.name}, state: {job.state.name})")
        try:
            client.batches.cancel(name=job.name)
        except Exception:
            pass  # best-effort cleanup; a 1-line job is cheap regardless
    except Exception as e:  # noqa: BLE001 -- deliberately broad, reported
        print(f"  batch  FAIL -- {str(e).splitlines()[0][:300]}")


if __name__ == "__main__":
    main()
