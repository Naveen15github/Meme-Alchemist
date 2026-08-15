"""Delete tokens.

The API is public and unauthenticated, so "who may delete this meme?" cannot
be answered with an identity. Instead, creating a meme mints a random token
that is returned to that browser exactly once. Only the hash is stored, so a
leaked database row still does not let anyone delete anything.

This is capability-based, not identity-based: whoever holds the token may
delete, which is precisely "the browser that made it".
"""
import hashlib
import hmac
import secrets

TOKEN_BYTES = 24  # 192 bits, url-safe base64


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str, expected_hash: str) -> bool:
    """Constant-time comparison, so timing cannot be used to guess a token."""
    if not token or not expected_hash:
        return False
    return hmac.compare_digest(hash_token(token), expected_hash)
