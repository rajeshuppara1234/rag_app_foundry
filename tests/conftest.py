import time
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        app_env="development",
        public_origin="http://localhost:8000",
        auth_authority="https://test.ciamlogin.com/",
        auth_issuer="https://test.ciamlogin.com/tenant/v2.0",
        auth_jwks_url="https://test.ciamlogin.com/keys",
        auth_audience="api-client",
        auth_spa_client_id="spa-client",
        auth_scope="api://api-client/access_as_user",
        foundry_openai_endpoint="https://test.openai.azure.com/openai/v1/",
        foundry_chat_model="chat",
        azure_openai_endpoint="https://test.openai.azure.com/",
        azure_openai_embedding_deployment="embed",
        chroma_url="https://chroma.example",
        requests_per_minute=2,
    )


@pytest.fixture(scope="session")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def make_token(settings, signing_key):
    def token(**overrides):
        now = int(time.time())
        claims = {
            "sub": "user-one",
            "aud": settings.auth_audience,
            "iss": settings.auth_issuer,
            "exp": now + 300,
            "iat": now,
            "nbf": now,
            "ver": "2.0",
            "scp": "access_as_user",
            "azp": settings.auth_spa_client_id,
        }
        claims.update(overrides)
        return jwt.encode(
            claims, signing_key, algorithm="RS256", headers={"kid": "test-key"}
        )

    return token


@pytest.fixture
def api(settings, signing_key):
    service = Mock()
    service.ready.return_value = True
    service.answer.return_value = {
        "answer": "An answer [1]",
        "sources": [{"citation": 1, "source": "guide.pdf", "page": 2}],
    }
    app = create_app(settings, lambda _: service)
    with TestClient(app) as client:
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key(), as_dict=True)
        jwk.update(kid="test-key", use="sig", alg="RS256")
        app.state.token_validator.keys.fetch_data = lambda: {"keys": [jwk]}
        yield SimpleNamespace(client=client, service=service, app=app)
    service.close.assert_called_once()
