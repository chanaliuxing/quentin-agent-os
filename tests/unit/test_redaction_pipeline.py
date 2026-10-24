import pytest
from quentin.security.redaction_pipeline import RedactionPipeline

def test_redaction():
    pipeline = RedactionPipeline()
    text = "My email is test@example.com and my key is sk-123456789012345678901234567890123456789012345678"
    redacted = pipeline.redact(text)
    assert "[REDACTED]" in redacted
    assert "test@example.com" not in redacted
    assert "sk-" not in redacted
