import os
from quentin.llm.auth_profiles import get_auth_manager

def test_auth_bootstrap():
    print("--- Testing Auth Bootstrap ---")
    # Set dummy env
    os.environ["LLM_BASE_URL"] = "http://test-ollama:11434/api/generate"
    os.environ["LLM_API_KEY"] = "sk-test-key"
    
    # Force fresh instance
    import quentin.llm.auth_profiles
    quentin.llm.auth_profiles._MANAGER_INSTANCE = None
    
    mgr = get_auth_manager()
    profile = mgr.get_best_profile("ollama")
    
    print(f"Profile ID: {profile.profile_id}")
    print(f"Base URL: {profile.base_url}")
    print(f"Secret Ref: {profile.secret_ref}")
    
    assert "api/generate" not in profile.base_url
    assert profile.secret_ref == "LLM_API_KEY"
    print("Auth Bootstrap check PASSED.")

if __name__ == "__main__":
    test_auth_bootstrap()
