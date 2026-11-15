"""Environment loading shared by the application and dependency-free CLI."""

import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_environment(path: Path = ROOT / ".env.local") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise ValueError(f"Invalid environment line: {key}")
        parts = shlex.split(value, comments=True)
        if len(parts) > 1:
            raise ValueError(f"Quote the value of {key}")
        os.environ.setdefault(key.strip(), parts[0] if parts else "")


@dataclass(frozen=True)
class Settings:
    app_port: int
    ch_host: str
    ch_port: int
    ch_http_port: int
    ch_user: str
    ch_password: str
    ch_database: str

    @classmethod
    def from_environment(cls) -> "Settings":
        load_environment()
        settings = cls(
            app_port=int(os.environ["APP_PORT"]),
            ch_host=os.environ["CLICKHOUSE_HOST"],
            ch_port=int(os.environ["CLICKHOUSE_PORT"]),
            ch_http_port=int(os.environ["CLICKHOUSE_HTTP_PORT"]),
            ch_user=os.environ["CLICKHOUSE_USER"],
            ch_password=os.environ["CLICKHOUSE_PASSWORD"],
            ch_database=os.environ["CLICKHOUSE_DATABASE"],
        )
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", settings.ch_database):
            raise ValueError("Invalid CLICKHOUSE_DATABASE identifier")
        return settings
