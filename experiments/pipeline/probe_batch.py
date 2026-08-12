# -*- coding: utf-8 -*-
"""Probe the ACTUAL codepath the bake-off uses: batches.create.

probe_models.py checks synchronous generate_content access, which has been
observed to diverge from Batch API access for the same model on the same
key (gemini-2.5-flash-lite listed fine, 404'd specifically on
batches.create). This probe submits one tiny 1-line batch job per candidate
model and reports whether the job was accepted -- it does NOT wait for the
job to finish, just confirms Google accepted it, which is the point where
access actually gets checked.

    python -m pipeline.probe_batch
"""
import json
import os
import tempfile

from .models import MODEL_CONFIGS

CANDIDATES = list(MODEL_CONFIGS)


def main():
    from google import genai
    from google.genai import types

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set.")
    client = genai.Client(api_key=key)

    print(f"probing batches.create for {len(CANDIDATES)} models "
          f"(1-line job each, not awaited)...\n")

    tmp_dir = tempfile.mkdtemp(prefix="batch_probe_")
    ok, failed = [], []

    for model_name in CANDIDATES:
        jsonl_path = os.path.join(tmp_dir, f"{model_name}.jsonl")
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "key": "probe-0",
                "request": {"contents": [{"role": "user",
                                           "parts": [{"text": "Say OK."}]}]},
            }) + "\n")
        try:
            uploaded = client.files.upload(
                file=jsonl_path,
                config=types.UploadFileConfig(mime_type="application/jsonl"),
            )
            job = client.batches.create(
                model=model_name, src=uploaded.name,
                config={"display_name": f"probe-{model_name}"},
            )
            print(f"  OK    {model_name}  (job: {job.name}, state: {job.state.name})")
            ok.append(model_name)
            try:
                client.batches.cancel(name=job.name)
            except Exception:
                pass  # best-effort; a 1-line job is cheap even if it runs
        except Exception as e:  # noqa: BLE001 -- deliberately broad, reported
            msg = str(e).splitlines()[0][:500]
            print(f"  FAIL  {model_name}  -- {msg}")
            failed.append(model_name)

    print(f"\n{len(ok)} batch-accessible, {len(failed)} not, on this key.")
    if ok:
        print(f"use: python -m pipeline.bakeoff --models {' '.join(ok)}")


if __name__ == "__main__":
    main()
