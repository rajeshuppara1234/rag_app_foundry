import pytest
from pydantic import ValidationError
from app.config import Settings


@pytest.mark.parametrize(
    "change",
    [
        {"app_env": "production", "public_origin": "http://example.com"},
        {"auth_jwks_url": "http://keys.example.com"},
        {"auth_audience": "spa-client"},
        {"chroma_url": ""},
        {"foundry_chat_model": ""},
        {"auth_scope": "https://graph.microsoft.com/User.Read"},
    ],
)
def test_invalid_deployment_fails_closed(settings, change):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**settings.model_dump(), **change})


def test_authentication_configuration_is_required():
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
