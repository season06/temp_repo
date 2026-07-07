"""起 A2A MVP server。先設環境變數(見 examples/README.md),再 python examples/run_server.py。"""
import uvicorn
from a2a_mvp.config import Config
from a2a_mvp.server.app import build_app

if __name__ == "__main__":
    cfg = Config.from_env()
    print(f"serving on http://{cfg.host}:{cfg.port}  card: {cfg.public_url}/.well-known/agent-card.json")
    uvicorn.run(build_app(cfg), host=cfg.host, port=cfg.port)
