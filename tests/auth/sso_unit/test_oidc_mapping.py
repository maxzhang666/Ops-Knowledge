"""Unit tests for OIDC claim-mapping helpers.

Discovery / JWKS / token-exchange paths require a live IdP or httpx mocking +
full round-trip — covered in integration tests when Redis + IdP are available.
These tests focus on the pure-Python mapping logic which is easy to regress.
"""
from app.auth.models import UserRole
from app.auth.providers.oidc import _map_department, _map_role


def _claims(**extra):
    base = {"sub": "s", "email": "x@y", "groups": ["eng", "viewers"]}
    base.update(extra)
    return base


def test_map_role_picks_first_matched_group():
    cfg = {
        "group_claim": "groups",
        "role_map": {"eng": "system_admin", "viewers": "user"},
    }
    # First group that matches the role_map wins
    assert _map_role(cfg, _claims()) == UserRole.SYSTEM_ADMIN


def test_map_role_returns_none_when_no_match():
    cfg = {"group_claim": "groups", "role_map": {"ops": "system_admin"}}
    assert _map_role(cfg, _claims()) is None


def test_map_role_invalid_value_logged_and_skipped():
    cfg = {"group_claim": "groups", "role_map": {"eng": "not-a-role"}}
    # Invalid UserRole string → returns None rather than raising
    assert _map_role(cfg, _claims()) is None


def test_map_role_accepts_scalar_group_claim():
    cfg = {"group_claim": "role", "role_map": {"manager": "system_admin"}}
    assert _map_role(cfg, {"role": "manager"}) == UserRole.SYSTEM_ADMIN


def test_map_department_picks_first_matched():
    cfg = {
        "group_claim": "groups",
        "dept_map": {"eng": "Engineering", "viewers": "General"},
    }
    assert _map_department(cfg, _claims()) == "Engineering"


def test_map_department_none_when_no_match():
    cfg = {"group_claim": "groups", "dept_map": {"legal": "Legal"}}
    assert _map_department(cfg, _claims()) is None
