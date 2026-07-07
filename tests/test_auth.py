import time
import jwt
import pytest
from a2a_mvp.config import Config
from a2a_mvp.server.auth import verify_token, AuthError

CFG = Config(jwt_secret="testsecret", jwt_issuer="https://issuer.local",
             jwt_audience="a2a-mvp", jwt_algorithms=["HS256"])


def _mint(**over):
    claims = {"sub": "peer-agent", "iss": "https://issuer.local",
              "aud": "a2a-mvp", "exp": int(time.time()) + 60}
    claims.update(over)
    return jwt.encode(claims, "testsecret", algorithm="HS256")


def test_valid_token_returns_principal():
    p = verify_token(_mint(), CFG)
    assert p.subject == "peer-agent"


def test_expired_token_rejected():
    with pytest.raises(AuthError):
        verify_token(_mint(exp=int(time.time()) - 10), CFG)


def test_wrong_audience_rejected():
    with pytest.raises(AuthError):
        verify_token(_mint(aud="someone-else"), CFG)


def test_wrong_issuer_rejected():
    with pytest.raises(AuthError):
        verify_token(_mint(iss="https://evil"), CFG)


def test_bad_signature_rejected():
    bad = jwt.encode({"sub": "x", "iss": "https://issuer.local",
                      "aud": "a2a-mvp", "exp": int(time.time()) + 60},
                     "WRONGKEY", algorithm="HS256")
    with pytest.raises(AuthError):
        verify_token(bad, CFG)
