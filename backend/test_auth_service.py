import tempfile
from pathlib import Path

from auth_service import AuthService
from config_service import ConfigService


def _svc(tmp: str) -> AuthService:
    return AuthService(config=ConfigService(Path(tmp) / "config.yaml"))


def test_setup_login_and_reject_second_setup() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        svc = _svc(tmp)

        assert svc.is_configured() is False
        svc.setup("admin", "correct horse battery staple")
        assert svc.is_configured() is True

        assert svc.verify_login("admin", "correct horse battery staple") is True
        assert svc.verify_login("admin", "wrong password") is False
        assert svc.verify_login("nobody", "correct horse battery staple") is False

        try:
            svc.setup("admin", "another password here")
            assert False, "expected setup to reject a second call once configured"
        except ValueError:
            pass


def test_setup_rejects_short_password() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        svc = _svc(tmp)
        try:
            svc.setup("admin", "short")
            assert False, "expected short password to be rejected"
        except ValueError:
            pass


def test_change_password_requires_current_password() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        svc = _svc(tmp)
        svc.setup("admin", "correct horse battery staple")

        try:
            svc.change_password("wrong current", "new password here")
            assert False, "expected wrong current password to be rejected"
        except ValueError:
            pass

        svc.change_password("correct horse battery staple", "new password here")
        assert svc.verify_login("admin", "new password here") is True
        assert svc.verify_login("admin", "correct horse battery staple") is False


def test_enabled_defaults_true_and_respects_config() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        svc = _svc(tmp)
        assert svc.enabled() is True

        svc._config.update({"auth_enabled": False})
        assert svc.enabled() is False


def test_session_lifecycle() -> None:
    svc = AuthService()
    assert svc.is_valid_session(None) is False
    assert svc.is_valid_session("made-up-token") is False

    token = svc.create_session()
    assert svc.is_valid_session(token) is True

    svc.revoke_session(token)
    assert svc.is_valid_session(token) is False


if __name__ == "__main__":
    test_setup_login_and_reject_second_setup()
    test_setup_rejects_short_password()
    test_change_password_requires_current_password()
    test_enabled_defaults_true_and_respects_config()
    test_session_lifecycle()
    print("ok")
