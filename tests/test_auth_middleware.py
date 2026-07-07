import time
import jwt
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from a2a_mvp.config import Config
from a2a_mvp.server.auth import AuthMiddleware, current_principal

CFG = Config(jwt_secret="s", jwt_issuer="https://issuer.local",
             jwt_audience="a2a-mvp", jwt_algorithms=["HS256"])


def _mint():
    return jwt.encode({"sub": "peer", "iss": "https://issuer.local",
                       "aud": "a2a-mvp", "exp": int(time.time()) + 60},
                      "s", algorithm="HS256")


def _app():
    async def whoami(request):
        p = current_principal()
        return JSONResponse({"sub": p.subject if p else None})

    async def card(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/rpc", whoami, methods=["POST"]),
                            Route("/.well-known/agent-card.json", card)])
    app.add_middleware(AuthMiddleware, config=CFG,
                       exempt_paths=["/.well-known/agent-card.json"])
    return TestClient(app)


def test_missing_token_401():
    r = _app().post("/rpc")
    assert r.status_code == 401
    assert r.headers["www-authenticate"].lower().startswith("bearer")


def test_valid_token_sets_principal():
    r = _app().post("/rpc", headers={"Authorization": f"Bearer {_mint()}"})
    assert r.status_code == 200
    assert r.json()["sub"] == "peer"


def test_card_path_exempt():
    r = _app().get("/.well-known/agent-card.json")
    assert r.status_code == 200
