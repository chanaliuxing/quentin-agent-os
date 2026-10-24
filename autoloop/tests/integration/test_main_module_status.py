from app.main import get_main_status


def test_get_main_status_integration_contract():
    assert get_main_status() == "ok"
