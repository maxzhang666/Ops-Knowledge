import hashlib
import hmac

import pytest

from app.workflow.webhook_service import WebhookAuthFailed, WebhookService


def test_auth_none_passes():
    WebhookService.verify({"auth_type": "none"}, headers={}, raw_body=b"", client_ip="1.2.3.4")


def test_ip_allowlist_blocks():
    with pytest.raises(WebhookAuthFailed, match="not allowed"):
        WebhookService.verify(
            {"auth_type": "none", "allowed_ips": ["10.0.0.1"]},
            headers={}, raw_body=b"", client_ip="1.2.3.4",
        )


def test_bearer_match():
    WebhookService.verify(
        {"auth_type": "bearer", "secret": "s3cr3t"},
        headers={"authorization": "Bearer s3cr3t"}, raw_body=b"", client_ip="",
    )


def test_bearer_mismatch():
    with pytest.raises(WebhookAuthFailed, match="bearer"):
        WebhookService.verify(
            {"auth_type": "bearer", "secret": "s3cr3t"},
            headers={"authorization": "Bearer wrong"}, raw_body=b"", client_ip="",
        )


def test_hmac_roundtrip():
    secret = "k"
    hook_id = "abc123"
    body = b'{"x":1}'
    sig = hmac.new(secret.encode(), body + hook_id.encode(), hashlib.sha256).hexdigest()
    WebhookService.verify(
        {"auth_type": "hmac", "secret": secret, "hook_id": hook_id},
        headers={"x-signature": f"sha256={sig}"}, raw_body=body, client_ip="",
    )


def test_hmac_mismatch():
    with pytest.raises(WebhookAuthFailed, match="hmac"):
        WebhookService.verify(
            {"auth_type": "hmac", "secret": "k", "hook_id": "abc"},
            headers={"x-signature": "sha256=deadbeef"}, raw_body=b"x", client_ip="",
        )


def test_unknown_auth_type_rejected():
    with pytest.raises(WebhookAuthFailed, match="unknown"):
        WebhookService.verify(
            {"auth_type": "totp", "secret": "x"},
            headers={}, raw_body=b"", client_ip="",
        )
