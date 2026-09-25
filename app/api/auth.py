"""Validate API access tokens, never ID tokens or unverified identity headers."""

from dataclasses import dataclass
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import Settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class User:
    subject: str


class TokenValidator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.keys = jwt.PyJWKClient(settings.auth_jwks_url, timeout=5, lifespan=300)

    def validate(self, token: str) -> User:
        try:
            if len(token) > 16384:
                raise jwt.InvalidTokenError("Oversized token")
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not header.get("kid"):
                raise jwt.InvalidTokenError("Unsupported signing algorithm")
            key = self.keys.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.settings.auth_audience,
                issuer=self.settings.auth_issuer,
                options={"require": ["exp", "iat", "nbf", "sub", "iss", "aud"]},
                leeway=30,
            )
        except jwt.PyJWKClientConnectionError:
            raise HTTPException(
                503, "Sign-in verification is temporarily unavailable"
            ) from None
        except jwt.PyJWTError:
            raise HTTPException(
                401,
                "Invalid or expired access token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None
        if claims.get("ver") != "2.0" or not isinstance(claims.get("scp"), str):
            raise HTTPException(403, "A delegated v2 API access token is required")
        if self.settings.auth_required_scope not in claims["scp"].split():
            raise HTTPException(403, "Required API permission is missing")
        if claims.get("azp") != self.settings.auth_spa_client_id:
            raise HTTPException(403, "Client application is not authorized")
        return User(subject=claims["sub"])


def current_user(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)
) -> User:
    if credentials is None:
        raise HTTPException(
            401, "Sign in to continue", headers={"WWW-Authenticate": "Bearer"}
        )
    return request.app.state.token_validator.validate(credentials.credentials)
