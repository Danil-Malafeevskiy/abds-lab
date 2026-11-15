"""Run with python3 -m app.cli; no third-party host dependencies are needed."""

import argparse
import sys
import time

from app.config import ROOT, Settings
from app.generator import generate
from app.http_clickhouse import HttpClickHouse
from app.schema import TABLES

DATA = ROOT / "data"


def create_schema(client: HttpClickHouse) -> None:
    database = client.settings.ch_database
    client.execute(f"CREATE DATABASE IF NOT EXISTS `{database}`", database=False)
    for name, table in TABLES.items():
        client.execute(table.ddl(database, name))
    print("Schema created.", flush=True)


def load(client: HttpClickHouse) -> None:
    missing = [str(DATA / f"{name}.csv") for name in TABLES if not (DATA / f"{name}.csv").is_file()]
    if missing:
        raise RuntimeError("CSV files missing. Run make gen first: " + ", ".join(missing))
    nonempty = [
        name for name in TABLES
        if int(client.execute(f"SELECT count() FROM `{name}`").strip())
    ]
    if nonempty:
        raise RuntimeError(
            "Load refused: tables are not empty (" + ", ".join(nonempty) + "). "
            "No rows were inserted. To rebuild the dataset, run make teardown && make setup.",
        )
    for name, table in TABLES.items():
        columns = ", ".join(f"`{column}`" for column in table.names)
        client.execute(f"INSERT INTO `{name}` ({columns}) FORMAT CSV", DATA / f"{name}.csv")
        print(f"Loaded {name}.", flush=True)


def teardown(client: HttpClickHouse) -> None:
    for name in reversed(TABLES):
        client.execute(f"DROP TABLE IF EXISTS `{name}` SYNC")
    print("Tables and ClickHouse data removed. Generated CSV files remain in data/.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("schema", "gen", "load", "setup", "teardown"))
    command = parser.parse_args().command
    started = time.perf_counter()
    try:
        settings = Settings.from_environment()
        client = HttpClickHouse(settings)
        if command in ("schema", "setup"):
            create_schema(client)
        if command in ("gen", "setup"):
            for name, count in generate(DATA, 42).items():
                print(f"Generated {name}: {count:,} rows.", flush=True)
        if command in ("load", "setup"):
            load(client)
        if command == "teardown":
            teardown(client)
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"{command} completed in {time.perf_counter() - started:.2f}s.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
