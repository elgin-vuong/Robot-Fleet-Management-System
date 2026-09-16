from backend.app.agent.agent import _role_may_use


def test_viewer_may_use_read_tools():
    assert _role_may_use("read", "viewer") is True


def test_operator_may_use_read_tools():
    assert _role_may_use("read", "operator") is True


def test_admin_may_use_read_tools():
    assert _role_may_use("read", "admin") is True


def test_viewer_may_not_use_write_tools():
    assert _role_may_use("write", "viewer") is False


def test_operator_may_use_write_tools():
    assert _role_may_use("write", "operator") is True


def test_admin_may_use_write_tools():
    assert _role_may_use("write", "admin") is True
