"""Validation surface for the SsoSettings Pydantic schema (plan24 Task 4).

Admin save path POST /system/settings/update validates against this before
writing to runtime_config; typos here become 400s rather than silent config
drift that OIDCAuthProvider swallows at login time.
"""
import pytest
from pydantic import ValidationError

from app.system.schemas import SsoSettings


def test_defaults_roundtrip():
    s = SsoSettings()
    assert s.enabled is False
    assert s.scopes == "openid profile email"
    assert s.group_claim == "groups"
    assert s.role_map == {}


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        SsoSettings.model_validate({"enabled": True, "unknown_field": "x"})


def test_role_map_is_plain_dict():
    s = SsoSettings.model_validate({
        "enabled": True,
        "issuer": "https://idp.example.com",
        "client_id": "test",
        "redirect_uri": "https://app.example.com/cb",
        "role_map": {"admin-group": "system_admin", "everyone": "user"},
    })
    assert s.role_map["admin-group"] == "system_admin"
    assert s.role_map["everyone"] == "user"


def test_dept_map_is_plain_dict():
    s = SsoSettings.model_validate({
        "enabled": True,
        "dept_map": {"eng": "Engineering", "ops": "Ops"},
    })
    assert s.dept_map["eng"] == "Engineering"


def test_partial_config_fills_defaults():
    s = SsoSettings.model_validate({"enabled": True, "issuer": "https://x"})
    assert s.button_label == "使用 SSO 登录"
    assert s.scopes == "openid profile email"
