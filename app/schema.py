"""ClickHouse table schemas and CSV column order."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Table:
    columns: tuple[tuple[str, str], ...]
    engine: str
    order_by: str
    partition_by: str = ""

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.columns)

    def ddl(self, database: str, name: str) -> str:
        columns = ", ".join(f"`{column}` {typ}" for column, typ in self.columns)
        partition = f"PARTITION BY {self.partition_by}" if self.partition_by else ""
        return (
            f"CREATE TABLE IF NOT EXISTS `{database}`.`{name}` ({columns}) "
            f"ENGINE = {self.engine} {partition} ORDER BY {self.order_by}"
        )


TABLES = {
    "dim_realty": Table(
        (("id", "UInt64"), ("address", "String"), ("square", "UInt32"),
         ("type", "String"), ("number", "String"), ("rooms", "UInt8"),
         ("floor", "UInt8"), ("porch", "UInt8"), ("created_at", "DateTime")),
        "MergeTree", "id",
    ),
    "dim_gauges": Table(
        (("id", "UInt64"), ("name", "String"), ("country", "String"),
         ("created_at", "DateTime")),
        "MergeTree", "id",
    ),
    "dim_tariffs": Table(
        (("id", "UInt64"), ("name", "String"), ("price_day_kwph", "UInt32"),
         ("price_night_kwph", "UInt32"), ("valid_from", "DateTime"),
         ("valid_to", "DateTime"), ("created_at", "DateTime"), ("updated_at", "DateTime")),
        "ReplacingMergeTree(updated_at)", "(id, valid_from)",
    ),
    "dim_users": Table(
        (("id", "UInt64"), ("fio", "String"), ("phone", "String"),
         ("phone_prev", "String"), ("created_at", "DateTime"), ("updated_at", "DateTime")),
        "ReplacingMergeTree(updated_at)", "id",
    ),
    "fact_gauge_bindings": Table(
        (("gauge_id", "UInt64"), ("realty_id", "UInt64"), ("created_at", "DateTime"),
         ("sign", "Int8"), ("version", "UInt64")),
        "VersionedCollapsingMergeTree(sign, version)", "(realty_id, gauge_id)",
    ),
    "fact_meter_readings": Table(
        (("realty_id", "UInt64"), ("user_id", "UInt64"), ("tariff_id", "UInt64"),
         ("gauge_id", "UInt64"), ("reading_date", "Date"), ("day_kw", "UInt32"),
         ("night_kw", "UInt32"), ("created_at", "DateTime")),
        "ReplacingMergeTree(created_at)", "(realty_id, reading_date)", "toYYYYMM(reading_date)",
    ),
    "fact_invoice": Table(
        (("realty_id", "UInt64"), ("user_id", "UInt64"), ("tariff_id", "UInt64"),
         ("gauge_id", "UInt64"), ("day_kw", "UInt32"), ("night_kw", "UInt32"),
         ("price", "UInt64"), ("deadline", "Date"), ("created_at", "DateTime")),
        "MergeTree", "(realty_id, created_at)", "toYYYYMM(created_at)",
    ),
}
