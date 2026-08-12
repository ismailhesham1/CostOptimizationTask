# -*- coding: utf-8 -*-
"""Test exactly the 3 target models on the current key: sync access AND
real batch access, in one small run. Narrower than probe_models.py /
probe_batch.py (which sweep every candidate) -- use this once you've got a
new key and just want a fast yes/no on gemini-2.5-flash-lite,
gemini-3.1-flash-lite, gemini-2.5-pro specifically.

    python -m pipeline.probe_three
"""
import json
import os
import tempfile

MODELS = ["gemini-2.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-pro"]


def check_sync(client, model_name):
    from google.genai import types
    try:
        client.models.generate_content(
            model=model_name, contents="Say OK.",
            config=types.GenerateContentConfig(max_output_tokens=5),
        )
        return True, ""
    except Exception as e:  # noqa: BLE001 -- deliberately broad, reported
        return False, str(e).splitlines()[0][:300]


def check_batch(client, model_name, tmp_dir):
    from google.genai import types
    path = os.path.join(tmp_dir, f"{model_name}.jsonl")
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
            model=model_name, src=uploaded.name,
            config={"display_name": f"probe3-{model_name}"})
        try:
            client.batches.cancel(name=job.name)
        except Exception:
            pass  # best-effort cleanup; a 1-line job is cheap regardless
        return True, ""
    except Exception as e:  # noqa: BLE001 -- deliberately broad, reported
        return False, str(e).splitlines()[0][:300]


def main():
    from google import genai

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set.")
    client = genai.Client(api_key=key)
    tmp_dir = tempfile.mkdtemp(prefix="probe_three_")

    print(f"{'model':<24}{'sync':<8}{'batch':<8}")
    print("-" * 60)
    usable = []
    for model_name in MODELS:
        sync_ok, sync_err = check_sync(client, model_name)
        batch_ok, batch_err = check_batch(client, model_name, tmp_dir)
        print(f"{model_name:<24}{'OK' if sync_ok else 'FAIL':<8}"
              f"{'OK' if batch_ok else 'FAIL':<8}")
        if not sync_ok:
            print(f"    sync  -- {sync_err}")
        if not batch_ok:
            print(f"    batch -- {batch_err}")
        if sync_ok and batch_ok:
            usable.append(model_name)

    print("-" * 60)
    if usable:
        print(f"use: python -m pipeline.bakeoff --models {' '.join(usable)}")
    else:
        print("none of the 3 models are batch-usable on this key yet.")


if __name__ == "__main__":
    main()
