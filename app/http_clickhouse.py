"""Small stdlib HTTP client for CSV loading and SQL checks on the host."""

import base64
import http.client
import json
import os
from pathlib import Path
from urllib.parse import urlencode

from app.config import Settings


class HttpClickHouse:
    def __init__(self, settings: Settings):
        self.settings = settings

    def execute(self, query: str, csv_file: Path | None = None, *, database: bool = True) -> bytes:
        options = {"query": query, "output_format_json_quote_64bit_integers": "0"}
        if database:
            options["database"] = self.settings.ch_database
        credentials = f"{self.settings.ch_user}:{self.settings.ch_password}".encode()
        headers = {"Authorization": "Basic " + base64.b64encode(credentials).decode()}
        connection = http.client.HTTPConnection(
            self.settings.ch_host, self.settings.ch_http_port, timeout=120,
        )
        try:
            if csv_file is None:
                connection.request("POST", "/?" + urlencode(options), body=b"", headers=headers)
            else:
                with csv_file.open("rb") as stream:
                    headers["Content-Length"] = str(os.fstat(stream.fileno()).st_size)
                    connection.request("POST", "/?" + urlencode(options), body=stream, headers=headers)
            response = connection.getresponse()
            body = response.read()
            if response.status != 200:
                raise RuntimeError(f"ClickHouse HTTP {response.status}: {body.decode()[:1000]}")
            return body
        finally:
            connection.close()

    def rows(self, query: str) -> list[dict]:
        return [json.loads(line) for line in self.execute(query + " FORMAT JSONEachRow").splitlines()]
