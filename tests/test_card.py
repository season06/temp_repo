from a2a_mvp.config import Config
from a2a_mvp.server.card import build_agent_card

CFG = Config(public_url="http://127.0.0.1:9999")


def test_card_has_identity_and_skill():
    card = build_agent_card(CFG)
    data = card.model_dump(by_alias=True, exclude_none=True)
    assert data["url"].startswith("http://127.0.0.1:9999")
    assert data["capabilities"]["streaming"] is False
    assert len(data["skills"]) >= 1


def test_card_advertises_bearer_security():
    data = build_agent_card(CFG).model_dump(by_alias=True, exclude_none=True)
    schemes = data.get("securitySchemes", {})
    dumped = str(schemes).lower()
    assert "bearer" in dumped or "http" in dumped
