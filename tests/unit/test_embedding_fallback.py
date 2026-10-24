from quentin.infra.llm.embeddings import FallbackEmbeddingClient


class _OkClient:
    def __init__(self, vec):
        self._vec = vec

    def embed_text(self, text: str):
        return list(self._vec)

    @property
    def dim(self) -> int:
        return len(self._vec)


class _FailClient:
    def embed_text(self, text: str):
        raise RuntimeError("boom")

    @property
    def dim(self) -> int:
        return 0


def test_fallback_returns_first_success() -> None:
    client = FallbackEmbeddingClient(
        providers=[_FailClient(), _OkClient([0.1, 0.2])],
        provider_names=["fail", "ok"],
        retries=[1, 1],
    )
    vec = client.embed_text("hello")
    assert vec == [0.1, 0.2]


def test_fallback_empty_when_all_fail() -> None:
    client = FallbackEmbeddingClient(
        providers=[_FailClient(), _FailClient()],
        provider_names=["a", "b"],
        retries=[1, 1],
    )
    vec = client.embed_text("hello")
    assert vec == []
