import uvicorn
from a2a_mvp.config import Config
from a2a_mvp.server.app import build_app
from a2a_mvp.telemetry import configure_tracing


def main():
    config = Config.from_env()
    configure_tracing(config)
    uvicorn.run(build_app(config), host=config.host, port=config.port)


if __name__ == "__main__":
    main()
