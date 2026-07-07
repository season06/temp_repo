import time
import jwt
from starlette.testclient import TestClient
from a2a_mvp.config import Config
from a2a_mvp.server.app import build_app
from tests.stub import make_stub

CFG = Config(jwt_secret="s", jwt_issuer="https://issuer.local",
             jwt_audience="a2a-mvp", jwt_algorithms=["HS256"])


def _token():
    return jwt.encode({"sub": "peer", "iss": "https://issuer.local",
                       "aud": "a2a-mvp", "exp": int(time.time()) + 60},
                      "s", algorithm="HS256")


def _client():
    return TestClient(build_app(CFG, model=make_stub("e2e reply")))


def test_agent_card_reachable_without_auth():
    r = _client().get("/.well-known/agent-card.json")
    assert r.status_code == 200
    assert "A2A MVP DeepAgent" in r.text


def test_rpc_without_token_401():
    r = _client().post("/", json={"jsonrpc": "2.0", "id": "1",
                                  "method": "message/send", "params": {}})
    assert r.status_code == 401


def test_rpc_with_token_reaches_agent():
    body = {
        "jsonrpc": "2.0", "id": "1", "method": "message/send",
        "params": {"message": {"role": "user",
                               "parts": [{"kind": "text", "text": "hi"}],
                               "messageId": "m1"}},
    }
    r = _client().post("/", json=body, headers={"Authorization": f"Bearer {_token()}"})
    assert r.status_code == 200
    assert "e2e reply" in r.text
