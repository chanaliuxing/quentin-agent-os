from __future__ import annotations

import json
import time
from typing import Dict, List, Sequence, Tuple

import httpx


def build_embedding_jsonl(*, model: str, texts: Sequence[str]) -> bytes:
    lines: List[str] = []
    for i, text in enumerate(texts):
        req = {
            "custom_id": f"req_{i}",
            "method": "POST",
            "url": "/v1/embeddings",
            "body": {"model": model, "input": text},
        }
        lines.append(json.dumps(req, ensure_ascii=False))
    return "\n".join(lines).encode("utf-8")


def upload_batch_file(
    *,
    client: httpx.Client,
    base_url: str,
    headers: Dict[str, str],
    model: str,
    texts: Sequence[str],
) -> str:
    files = {"file": ("memory_embeddings.jsonl", build_embedding_jsonl(model=model, texts=texts), "application/jsonl")}
    data = {"purpose": "batch"}
    resp = client.post(f"{base_url}/files", headers=headers, data=data, files=files)
    resp.raise_for_status()
    payload = resp.json() or {}
    file_id = str(payload.get("id") or "").strip()
    if not file_id:
        raise RuntimeError("openai batch file upload returned missing id")
    return file_id


def create_batch_job(
    *,
    client: httpx.Client,
    base_url: str,
    headers: Dict[str, str],
    input_file_id: str,
) -> Tuple[str, str, str]:
    create_payload = {
        "input_file_id": input_file_id,
        "endpoint": "/v1/embeddings",
        "completion_window": "24h",
        "metadata": {"source": "quentin-memory"},
    }
    create = client.post(f"{base_url}/batches", json=create_payload, headers=headers)
    create.raise_for_status()
    info = create.json() or {}
    batch_id = str(info.get("id") or "").strip()
    if not batch_id:
        raise RuntimeError("openai async batch create returned missing id")
    status = str(info.get("status") or "").strip().lower()
    output_file_id = str(info.get("output_file_id") or "").strip()
    return batch_id, status, output_file_id


def wait_batch_output_file(
    *,
    client: httpx.Client,
    base_url: str,
    headers: Dict[str, str],
    batch_id: str,
    poll_interval_s: float,
    timeout_s: float,
) -> str:
    deadline = time.time() + max(1.0, float(timeout_s))
    poll_interval = max(0.1, float(poll_interval_s))
    while time.time() < deadline:
        resp = client.get(f"{base_url}/batches/{batch_id}", headers=headers)
        resp.raise_for_status()
        body = resp.json() or {}
        state = str(body.get("status") or "").strip().lower()
        if state == "completed":
            output_file_id = str(body.get("output_file_id") or "").strip()
            if not output_file_id:
                raise RuntimeError(f"openai batch {batch_id} completed without output file")
            return output_file_id
        if state in {"failed", "expired", "cancelled", "canceled"}:
            raise RuntimeError(f"openai batch {batch_id} {state}")
        time.sleep(poll_interval)
    raise RuntimeError(f"openai batch {batch_id} timed out")


def fetch_output_lines(
    *,
    client: httpx.Client,
    base_url: str,
    headers: Dict[str, str],
    output_file_id: str,
) -> List[dict]:
    resp = client.get(f"{base_url}/files/{output_file_id}/content", headers=headers)
    resp.raise_for_status()
    text = resp.text or ""
    lines: List[dict] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        lines.append(json.loads(s))
    return lines
