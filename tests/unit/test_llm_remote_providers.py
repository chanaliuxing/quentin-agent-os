import pytest


class _FakeResponse:
    def __init__(self, *, status_code: int, json_data: dict, text: str = ""):
        self.status_code = status_code
        self._json = json_data
        self.text = text or ""

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class _FakeClient:
    def __init__(self, *, timeout: float):
        self.timeout = timeout
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if url.endswith("/chat/completions"):
            return _FakeResponse(
                status_code=200,
                json_data={"choices": [{"message": {"content": "ok-openai"}}]},
            )
        if ":generateContent" in url:
            return _FakeResponse(
                status_code=200,
                json_data={
                    "candidates": [
                        {"content": {"parts": [{"text": "ok-gemini"}]}}
                    ]
                },
            )
        return _FakeResponse(status_code=500, json_data={}, text="unexpected_url")


def test_call_llm_openai_remote(monkeypatch):
    from quentin.llm import client as llm_client

    fake = _FakeClient(timeout=1.0)

    def _client_factory(*, timeout: float):
        # keep one instance so we can inspect calls
        fake.timeout = timeout
        return fake

    monkeypatch.setattr(llm_client.httpx, "Client", _client_factory)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    out = llm_client.call_llm("gpt-4o-mini", user_prompt="hi", system_prompt="sys")
    assert out == "ok-openai"
    assert fake.calls, "expected at least one http call"
    req = fake.calls[0]
    assert req["url"].endswith("/chat/completions")
    assert req["headers"]["Authorization"] == "Bearer sk-test"
    assert req["json"]["model"] == "gpt-4o-mini"


def test_call_llm_gemini_remote(monkeypatch):
    from quentin.llm import client as llm_client

    fake = _FakeClient(timeout=1.0)

    def _client_factory(*, timeout: float):
        fake.timeout = timeout
        return fake

    monkeypatch.setattr(llm_client.httpx, "Client", _client_factory)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    monkeypatch.setenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")

    out = llm_client.call_llm("gemini-2.5-flash", user_prompt="hi", system_prompt="sys")
    assert out == "ok-gemini"
    assert fake.calls, "expected at least one http call"
    req = fake.calls[0]
    assert ":generateContent" in req["url"]
    assert "key=g-test" in req["url"]


@pytest.mark.parametrize(
    "provider,env_key,env_base",
    [
        ("deepseek", "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"),
        ("openrouter", "OPENAI_API_KEY", "OPENAI_BASE_URL"),
    ],
)
def test_call_llm_openai_compat_providers(monkeypatch, provider, env_key, env_base):
    from quentin.llm import client as llm_client

    fake = _FakeClient(timeout=1.0)

    def _client_factory(*, timeout: float):
        fake.timeout = timeout
        return fake

    monkeypatch.setattr(llm_client.httpx, "Client", _client_factory)
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv(env_key, "sk-test")
    monkeypatch.setenv(env_base, "https://example.com/v1")

    out = llm_client.call_llm("deepseek-v3", user_prompt="hi", system_prompt="sys")
    assert out == "ok-openai"
