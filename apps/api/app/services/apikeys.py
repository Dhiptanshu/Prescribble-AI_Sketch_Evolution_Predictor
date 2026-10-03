"""API key generation and lookup. A key is 'prs_sk_' + 32 random URL-safe characters (192 bits), shown once and stored only as a hash."""
import hashlib
import secrets

KEY_PREFIX = "prs_sk_"
_DISPLAY = len(KEY_PREFIX) + 4            # what is kept for display: 'prs_sk_ab12'


def generate_key() -> tuple[str, str, str]:
    """(full key, display prefix, sha256 hex digest)."""
    key = KEY_PREFIX + secrets.token_urlsafe(24)
    return key, key[:_DISPLAY], hash_key(key)


def hash_key(key: str) -> str:
    # Keys carry 192 bits of randomness, so a fast hash is the right tool (a slow password hash would only add latency).
    return hashlib.sha256(key.encode()).hexdigest()


def looks_like_key(value: str) -> bool:
    return value.startswith(KEY_PREFIX) and 20 <= len(value) <= 80
