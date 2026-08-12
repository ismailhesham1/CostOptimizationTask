# -*- coding: utf-8 -*-
"""Thin wrapper around the Gemini Batch API: build JSONL, submit, poll,
resume, download, parse. Requires `pip install google-genai` and the
GEMINI_API_KEY environment variable (never pass the key as a literal or CLI
argument -- the SDK's default Client() picks it up from the environment).
"""
import json
import os
import time

from .models import MODEL_CONFIGS
from .prompts import build_prompt, RESPONSE_SCHEMA


def get_client():
    from google import genai  # imported lazily so --dry-run needs no SDK
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit(
            "GEMINI_API_KEY is not set. Set it as an environment variable "
            "before running (see pipeline/README.md) -- never pass it on "
            "the command line."
        )
    return genai.Client(api_key=key)


def build_jsonl(chunks, model_name, direction, glossary_terms, use_glossary,
                 out_path):
    """chunks: list of list[(id, token, slot)].
    Writes one JSONL line per chunk. Returns {chunk_key: [(id, token, slot)]}
    so callers can map results back to source tokens."""
    cfg = MODEL_CONFIGS[model_name]
    key_map = {}
    with open(out_path, "w", encoding="utf-8") as f:
        for i, chunk in enumerate(chunks):
            chunk_key = f"{direction}-{i}"
            key_map[chunk_key] = chunk
            prompt = build_prompt(direction, chunk, glossary_terms, use_glossary)
            request = {
                "key": chunk_key,
                "request": {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        **cfg["generation_config"],
                        "responseSchema": RESPONSE_SCHEMA,
                    },
                },
            }
            f.write(json.dumps(request, ensure_ascii=False) + "\n")
    return key_map


def submit_batch(client, jsonl_path, model_name, display_name, job_file):
    """Uploads the JSONL and creates the batch job. Persists the job name to
    `job_file` immediately so a crash mid-poll can resume instead of
    resubmitting and paying twice."""
    from google.genai import types
    uploaded = client.files.upload(
        file=jsonl_path,
        config=types.UploadFileConfig(mime_type="application/jsonl"),
    )
    job = client.batches.create(
        model=model_name,
        src=uploaded.name,
        config={"display_name": display_name},
    )
    with open(job_file, "w", encoding="utf-8") as f:
        json.dump({"job_name": job.name, "model": model_name}, f)
    return job


def resume_or_submit(client, jsonl_path, model_name, display_name, job_file):
    """If a job was already submitted (job_file exists), reattach to it
    instead of resubmitting. Call this instead of submit_batch directly."""
    if os.path.exists(job_file):
        with open(job_file, encoding="utf-8") as f:
            saved = json.load(f)
        print(f"  resuming existing job: {saved['job_name']}")
        return client.batches.get(name=saved["job_name"])
    return submit_batch(client, jsonl_path, model_name, display_name, job_file)


def poll_until_done(client, job, interval_s=30, timeout_s=6 * 3600):
    """Blocks, polling batches.get(), until the job reaches a terminal state."""
    terminal = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED",
                "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}
    waited = 0
    while job.state.name not in terminal:
        time.sleep(interval_s)
        waited += interval_s
        job = client.batches.get(name=job.name)
        print(f"  ... {job.state.name} ({waited}s elapsed)")
        if waited > timeout_s:
            raise TimeoutError(f"batch job {job.name} exceeded {timeout_s}s")
    if job.state.name != "JOB_STATE_SUCCEEDED":
        raise RuntimeError(f"batch job {job.name} ended in {job.state.name}")
    return job


def download_results(client, job):
    """Returns list of parsed per-line results:
    [{"key": ..., "response": {...parsed json...}, "usage": {...}}]
    Any line that fails to parse is returned with response=None so callers
    can re-queue it -- never let one bad line fail the whole run."""
    raw = client.files.download(file=job.dest.file_name)
    out = []
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        entry = {"key": rec.get("key"), "response": None, "usage": None}
        try:
            resp = rec["response"]
            usage = resp.get("usageMetadata", {})
            entry["usage"] = {
                "prompt_tokens": usage.get("promptTokenCount", 0),
                "output_tokens": usage.get("candidatesTokenCount", 0),
                "thinking_tokens": usage.get("thoughtsTokenCount", 0),
                "total_tokens": usage.get("totalTokenCount", 0),
            }
            text = resp["candidates"][0]["content"]["parts"][0]["text"]
            entry["response"] = json.loads(text)
        except Exception as e:  # noqa: BLE001 -- deliberately broad, logged
            entry["error"] = str(e)
        out.append(entry)
    return out
