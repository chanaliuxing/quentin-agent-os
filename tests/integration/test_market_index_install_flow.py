import pytest
from quentin.platform.registry.market_index import MarketIndex, PluginInfo

def test_market_publish_and_resolve():
    market = MarketIndex()
    
    plugin = PluginInfo(
        id="nlp-pack-v1",
        name="NLP Tools",
        version="1.0.5",
        publisher="OpenAI",
        download_url="https://example.com/nlp.zip",
        manifest_signature="sig_abc_123"
    )
    
    # 1. Publish
    market.publish(plugin)
    
    # 2. Search
    results = market.search("NLP")
    assert len(results) == 1
    assert results[0].publisher == "OpenAI"
    
    # 3. Resolve
    resolved = market.resolve("nlp-pack-v1")
    assert resolved.version == "1.0.5"
    assert resolved.manifest_signature == "sig_abc_123"
