from contextvars import ContextVar
from dataclasses import dataclass, field
import jwt
from jwt import PyJWKClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    subject: str
    claims: dict = field(default_factory=dict)


def _signing_key(token, config):
    if config.jwt_jwks_url:
        return PyJWKClient(config.jwt_jwks_url).get_signing_key_from_jwt(token).key
    if config.jwt_public_key:
        return config.jwt_public_key
    return config.jwt_secret


def verify_token(token, config):
    try:
        claims = jwt.decode(
            token,
            _signing_key(token, config),
            algorithms=config.jwt_algorithms,
            audience=config.jwt_audience,
            issuer=config.jwt_issuer,
            options={"require": ["exp", "iss", "aud"]},
        )
    except Exception as exc:
        raise AuthError("invalid token") from exc
    return Principal(subject=claims.get("sub", ""), claims=claims)


_principal_var = ContextVar("a2a_principal", default=None)


def current_principal():
    return _principal_var.get()


def _unauthorized(detail):
    return JSONResponse({"error": detail}, status_code=401,
                        headers={"WWW-Authenticate": "Bearer"})


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config, exempt_paths=None):
        super().__init__(app)
        self.config = config
        self.exempt_paths = set(exempt_paths or [])

    async def dispatch(self, request, call_next):
        if request.url.path in self.exempt_paths:
            return await call_next(request)
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return _unauthorized("missing bearer token")
        try:
            principal = verify_token(header[7:], self.config)
        except AuthError:
            return _unauthorized("invalid token")
        token = _principal_var.set(principal)
        try:
            return await call_next(request)
        finally:
            _principal_var.reset(token)
