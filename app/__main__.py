import uvicorn

from app.config import Settings


def main() -> None:
    settings = Settings.from_environment()
    uvicorn.run("app.api:app", host="0.0.0.0", port=settings.app_port, workers=1)


if __name__ == "__main__":
    main()
