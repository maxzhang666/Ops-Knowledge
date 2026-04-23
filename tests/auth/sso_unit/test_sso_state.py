"""PKCE pair correctness — the only part of sso_state testable without Redis."""
import base64
import hashlib

from app.auth.sso_state import _pkce_pair


def test_pkce_challenge_is_sha256_of_verifier():
    verifier, challenge = _pkce_pair()
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    assert challenge == expected


def test_pkce_values_unique_across_calls():
    v1, c1 = _pkce_pair()
    v2, c2 = _pkce_pair()
    assert v1 != v2
    assert c1 != c2


def test_pkce_verifier_is_url_safe_and_long():
    verifier, _ = _pkce_pair()
    # secrets.token_urlsafe(64) → at least ~85 chars after base64url encoding
    assert len(verifier) >= 80
    # base64url alphabet only (no + / =)
    assert set(verifier) <= set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    )
