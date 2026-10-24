from __future__ import annotations

from pathlib import Path

import httpx

from quentin.memory.embedding_batch import BatchEmbeddingConfig, BatchEmbeddingManager, EmbeddingCache


class _DummyEmbeddingClient:
    def embed_text(self, text: str):
        n = float(len(text))
        return [n, n + 1.0]


class _FakeGeminiClient:
    def __init__(self, *, get_payload: dict, upload_name: str = "files/new_in", batch_name: str = "batches/new", out_file: str = "files/new_out") -> None:
        self.get_payload = get_payload
        self.upload_name = upload_name
        self.batch_name = batch_name
        self.out_file = out_file
        self.post_calls = 0
        self.get_calls = 0

    def post(self, url: str, **kwargs):  # noqa: ANN003
        self.post_calls += 1
        req = httpx.Request("POST", url)
        if "upload" in url:
            return httpx.Response(200, request=req, json={"name": self.upload_name})
        return httpx.Response(
            200,
            request=req,
            json={
                "name": self.batch_name,
                "state": "SUCCEEDED",
                "outputConfig": {"file": self.out_file},
            },
        )

    def get(self, url: str, **kwargs):  # noqa: ANN003
        self.get_calls += 1
        req = httpx.Request("GET", url)
        return httpx.Response(200, request=req, json=self.get_payload)


def test_openai_async_resume_after_restart(tmp_path: Path, monkeypatch) -> None:
    cache = EmbeddingCache(tmp_path / "embed_cache.sqlite")
    job_path = tmp_path / "batch_jobs.sqlite"
    fp = "fp-chaos-openai-1"

    m1 = BatchEmbeddingManager(
        embedding_client=_DummyEmbeddingClient(),
        config=BatchEmbeddingConfig(
            provider="openai",
            model="m",
            provider_key="k",
            openai_async_batch_enabled=True,
            openai_api_key="sk",
            job_store_path=str(job_path),
        ),
        cache=cache,
    )
    assert m1.job_store is not None
    m1.job_store.upsert(
        fingerprint=fp,
        provider="openai",
        model="m",
        batch_id="batch_old",
        status="submitted",
    )

    # Simulate process restart with a new manager instance.
    m2 = BatchEmbeddingManager(
        embedding_client=_DummyEmbeddingClient(),
        config=BatchEmbeddingConfig(
            provider="openai",
            model="m",
            provider_key="k",
            openai_async_batch_enabled=True,
            openai_api_key="sk",
            job_store_path=str(job_path),
        ),
        cache=cache,
    )
    monkeypatch.setattr("quentin.memory.embedding_batch.wait_batch_output_file", lambda **kwargs: "out_resume")
    # If resume works, no new upload/create should happen.
    monkeypatch.setattr(m2, "_openai_async_upload_jsonl", lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not upload")))
    monkeypatch.setattr("quentin.memory.embedding_batch.create_batch_job", lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not create")))

    batch_id, out_id = m2._openai_async_submit_and_wait(
        client=httpx.Client(),
        base_url="https://api.openai.com/v1",
        model="m",
        headers={"Authorization": "Bearer sk"},
        texts=["hello"],
        batch_fingerprint=fp,
    )
    assert batch_id == "batch_old"
    assert out_id == "out_resume"
    row = m2.job_store.get(fp)
    assert row is not None
    assert row["status"] == "completed"


def test_openai_async_resume_failure_triggers_resubmit(tmp_path: Path, monkeypatch) -> None:
    cache = EmbeddingCache(tmp_path / "embed_cache.sqlite")
    job_path = tmp_path / "batch_jobs.sqlite"
    fp = "fp-chaos-openai-2"

    m = BatchEmbeddingManager(
        embedding_client=_DummyEmbeddingClient(),
        config=BatchEmbeddingConfig(
            provider="openai",
            model="m",
            provider_key="k",
            openai_async_batch_enabled=True,
            openai_api_key="sk",
            job_store_path=str(job_path),
        ),
        cache=cache,
    )
    assert m.job_store is not None
    m.job_store.upsert(
        fingerprint=fp,
        provider="openai",
        model="m",
        batch_id="batch_stuck",
        status="submitted",
    )

    monkeypatch.setattr(
        "quentin.memory.embedding_batch.wait_batch_output_file",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("resume timeout")),
    )
    monkeypatch.setattr(m, "_openai_async_upload_jsonl", lambda **kwargs: "file_new")
    monkeypatch.setattr(
        "quentin.memory.embedding_batch.create_batch_job",
        lambda **kwargs: ("batch_new", "completed", "out_new"),
    )

    batch_id, out_id = m._openai_async_submit_and_wait(
        client=httpx.Client(),
        base_url="https://api.openai.com/v1",
        model="m",
        headers={"Authorization": "Bearer sk"},
        texts=["hello"],
        batch_fingerprint=fp,
    )
    assert batch_id == "batch_new"
    assert out_id == "out_new"
    row = m.job_store.get(fp)
    assert row is not None
    assert row["batch_id"] == "batch_new"
    assert row["status"] == "completed"


def test_gemini_async_resume_after_restart(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path / "embed_cache.sqlite")
    job_path = tmp_path / "batch_jobs.sqlite"
    fp = "fp-chaos-gemini-1"

    m1 = BatchEmbeddingManager(
        embedding_client=_DummyEmbeddingClient(),
        config=BatchEmbeddingConfig(
            provider="gemini",
            model="text-embedding-004",
            provider_key="k",
            gemini_async_batch_enabled=True,
            gemini_api_key="gk",
            job_store_path=str(job_path),
        ),
        cache=cache,
    )
    assert m1.job_store is not None
    m1.job_store.upsert(
        fingerprint=fp,
        provider="gemini",
        model="text-embedding-004",
        batch_id="batches/old",
        status="submitted",
    )

    m2 = BatchEmbeddingManager(
        embedding_client=_DummyEmbeddingClient(),
        config=BatchEmbeddingConfig(
            provider="gemini",
            model="text-embedding-004",
            provider_key="k",
            gemini_async_batch_enabled=True,
            gemini_api_key="gk",
            job_store_path=str(job_path),
        ),
        cache=cache,
    )
    client = _FakeGeminiClient(get_payload={"state": "SUCCEEDED", "outputConfig": {"file": "files/out_resume"}})
    batch_id, out_id = m2._gemini_async_submit_and_wait(
        client=client,
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="gk",
        model="text-embedding-004",
        texts=["hello"],
        batch_fingerprint=fp,
    )
    assert batch_id == "batches/old"
    assert out_id == "files/out_resume"
    assert client.post_calls == 0


def test_gemini_async_resume_failure_triggers_resubmit(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path / "embed_cache.sqlite")
    job_path = tmp_path / "batch_jobs.sqlite"
    fp = "fp-chaos-gemini-2"

    m = BatchEmbeddingManager(
        embedding_client=_DummyEmbeddingClient(),
        config=BatchEmbeddingConfig(
            provider="gemini",
            model="text-embedding-004",
            provider_key="k",
            gemini_async_batch_enabled=True,
            gemini_api_key="gk",
            job_store_path=str(job_path),
        ),
        cache=cache,
    )
    assert m.job_store is not None
    m.job_store.upsert(
        fingerprint=fp,
        provider="gemini",
        model="text-embedding-004",
        batch_id="batches/stuck",
        status="submitted",
    )

    client = _FakeGeminiClient(get_payload={"state": "FAILED"})
    batch_id, out_id = m._gemini_async_submit_and_wait(
        client=client,
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="gk",
        model="text-embedding-004",
        texts=["hello"],
        batch_fingerprint=fp,
    )
    assert batch_id == "batches/new"
    assert out_id == "files/new_out"
    assert client.post_calls >= 2
