import hashlib
import hmac
import secrets
import time

from config_service import ConfigService, config_service

SESSION_COOKIE = "litethaus_session"
SESSION_TTL_SECONDS = 7 * 24 * 3600
PBKDF2_ITERATIONS = 200_000
MIN_PASSWORD_LENGTH = 8


class AuthService:
    def __init__(self, config: ConfigService | None = None) -> None:
        self._config = config or config_service
        self._sessions: dict[str, float] = {}

    def is_configured(self) -> bool:
        return bool((self._config.load().get("auth") or {}).get("password_hash"))

    def enabled(self) -> bool:
        return bool(self._config.load().get("auth_enabled", True))

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
        return f"{PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"

    @staticmethod
    def _verify_password(password: str, stored: str) -> bool:
        try:
            iterations, salt_hex, hash_hex = stored.split("$")
            digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
            return hmac.compare_digest(digest.hex(), hash_hex)
        except (ValueError, AttributeError):
            return False

    @staticmethod
    def _check_credentials(username: str, password: str) -> None:
        if not username.strip():
            raise ValueError("username cannot be empty")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")

    def setup(self, username: str, password: str) -> None:
        if self.is_configured():
            raise ValueError("auth is already configured")
        self._check_credentials(username, password)
        self._config.update({"auth": {"username": username, "password_hash": self._hash_password(password)}})

    def verify_login(self, username: str, password: str) -> bool:
        auth = self._config.load().get("auth") or {}
        if not username or username != auth.get("username"):
            return False
        return self._verify_password(password, auth.get("password_hash", ""))

    def change_password(self, current_password: str, new_password: str) -> None:
        auth = self._config.load().get("auth") or {}
        if not self._verify_password(current_password, auth.get("password_hash", "")):
            raise ValueError("current password is incorrect")
        self._check_credentials(auth.get("username", ""), new_password)
        self._config.update({"auth": {"username": auth.get("username"), "password_hash": self._hash_password(new_password)}})

    def create_session(self) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = time.time() + SESSION_TTL_SECONDS
        return token

    def is_valid_session(self, token: str | None) -> bool:
        if not token:
            return False
        expiry = self._sessions.get(token)
        if expiry is None or expiry < time.time():
            self._sessions.pop(token, None)
            return False
        return True

    def revoke_session(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)


auth_service = AuthService()
