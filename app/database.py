"""ClickHouse access for the HTTP service; SQL parameters are always bound."""

import clickhouse_connect

from app.config import Settings
from app.schema import TABLES


class Database:
    def __init__(self, settings: Settings):
        self.client = clickhouse_connect.get_client(
            host=settings.ch_host, port=settings.ch_http_port,
            username=settings.ch_user, password=settings.ch_password,
            database=settings.ch_database,
            autogenerate_session_id=False,
        )

    def rows(self, query: str, **parameters) -> list[dict]:
        result = self.client.query(query, parameters=parameters)
        return [dict(zip(result.column_names, row)) for row in result.result_rows]

    def command(self, query: str, **parameters) -> None:
        self.client.command(query, parameters=parameters)

    def insert(self, table: str, rows: list[tuple]) -> None:
        self.client.insert(table, rows, column_names=TABLES[table].names)

    def exists(self, table: str, identifier: int) -> bool:
        return bool(self.rows(f"SELECT 1 FROM {table} WHERE id = {{id:UInt64}} LIMIT 1", id=identifier))

    def close(self) -> None:
        self.client.close()
