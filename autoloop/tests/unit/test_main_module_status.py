from app.main import get_main_status


def test_get_main_status_returns_ok_string():
    """说明: main 模块状态函数必须返回精确字符串 ok。"""
    result = get_main_status()

    assert result == "ok"
    assert isinstance(result, str)
