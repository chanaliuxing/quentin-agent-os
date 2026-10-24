import pytest
from quentin.compat.version_router import VersionRouter

def test_version_routing_and_fallback():
    router = VersionRouter()
    
    router.register_version("get_user", "v1", lambda: "v1_user")
    router.register_version("get_user", "v2", lambda: "v2_user")
    
    # 1. Direct version hit
    assert router.route("get_user", "v1") == "v1_user"
    assert router.route("get_user", "v2") == "v2_user"
    
    # 2. Fallback to latest for unknown version
    assert router.route("get_user", "v3") == "v2_user"
    
    # 3. Non-existent endpoint
    with pytest.raises(ValueError, match="No routes found"):
        router.route("unknown_api", "v1")
