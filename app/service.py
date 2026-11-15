"""SCD operations and energy usage read models."""

from datetime import date, datetime, timedelta
from threading import Lock
from zoneinfo import ZoneInfo

from app.database import Database
from app.models import ReadingCreate, UserPatch
from app.schema import TABLES


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class Service:
    def __init__(self, database: Database, timezone: str):
        self.db = database
        self.timezone = ZoneInfo(timezone)
        self.locks = [Lock() for _ in range(128)]

    def require(self, table: str, identifier: int) -> None:
        if not self.db.exists(table, identifier):
            raise ApiError(404, "Not found")

    def next_timestamp(self, previous: datetime | None = None) -> datetime:
        now = datetime.now(self.timezone).replace(microsecond=0)
        if previous is None:
            return now
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=self.timezone)
        return max(now, previous + timedelta(seconds=1))

    def user_snapshot(self, identifier: int) -> dict:
        rows = self.db.rows("SELECT * FROM dim_users FINAL WHERE id = {id:UInt64}", id=identifier)
        if not rows:
            raise ApiError(404, "Not found")
        return rows[0]

    def get_user(self, identifier: int) -> dict:
        row = self.user_snapshot(identifier)
        return {key: row[key] for key in ("id", "fio", "phone", "phone_prev")}

    def patch_user(self, identifier: int, patch: UserPatch) -> None:
        with self.locks[identifier % len(self.locks)]:
            row = self.user_snapshot(identifier)
            if patch.fio is not None and patch.fio != row["fio"]:
                self.db.command(
                    "ALTER TABLE dim_users UPDATE fio = {fio:String} "
                    "WHERE id = {id:UInt64} SETTINGS mutations_sync = 1",
                    fio=patch.fio, id=identifier,
                )
                row["fio"] = patch.fio
            if patch.phone is not None and patch.phone != row["phone"]:
                row["phone_prev"], row["phone"] = row["phone"], patch.phone
            row["updated_at"] = self.next_timestamp(row["updated_at"])
            self.db.insert("dim_users", [tuple(row[name] for name in TABLES["dim_users"].names)])

    def get_realty(self, identifier: int) -> dict:
        rows = self.db.rows(
            "SELECT id, address, square, type, number, rooms, floor, porch "
            "FROM dim_realty WHERE id = {id:UInt64} LIMIT 1", id=identifier,
        )
        if not rows:
            raise ApiError(404, "Not found")
        return rows[0]

    def add_reading(self, identifier: int, reading: ReadingCreate) -> None:
        with self.locks[identifier % len(self.locks)]:
            for table, linked_id in (
                ("dim_realty", identifier), ("dim_users", reading.user_id),
                ("dim_gauges", reading.gauge_id), ("dim_tariffs", reading.tariff_id),
            ):
                self.require(table, linked_id)
            rows = self.db.rows(
                "SELECT created_at FROM fact_meter_readings FINAL "
                "WHERE realty_id = {id:UInt64} AND reading_date = {day:Date}",
                id=identifier, day=reading.reading_date,
            )
            created_at = self.next_timestamp(rows[0]["created_at"] if rows else None)
            self.db.insert("fact_meter_readings", [(
                identifier, reading.user_id, reading.tariff_id, reading.gauge_id,
                reading.reading_date, reading.day_kw, reading.night_kw, created_at,
            )])

    def list_readings(self, identifier: int, start: date, end: date) -> dict:
        self.require("dim_realty", identifier)
        rows = self.db.rows(
            "SELECT reading_date, user_id, tariff_id, gauge_id, day_kw, night_kw "
            "FROM fact_meter_readings FINAL WHERE realty_id = {id:UInt64} "
            "AND toString(reading_date) >= {start:String} "
            "AND toString(reading_date) <= {end:String} ORDER BY reading_date",
            id=identifier, start=start.isoformat(), end=end.isoformat(),
        )
        return {"readings": rows, "count": len(rows)}

    def list_invoices(self, identifier: int, limit: int, offset: int) -> dict:
        self.require("dim_realty", identifier)
        total = self.db.rows(
            "SELECT count() AS total FROM fact_invoice WHERE realty_id = {id:UInt64}", id=identifier,
        )[0]["total"]
        rows = self.db.rows(
            "SELECT tariff_id, gauge_id, day_kw, night_kw, price, deadline, created_at "
            "FROM fact_invoice WHERE realty_id = {id:UInt64} ORDER BY created_at DESC "
            "LIMIT {limit:UInt64} OFFSET {offset:UInt64}",
            id=identifier, limit=min(limit, total), offset=min(offset, total),
        ) if limit and offset < total else []
        return {"invoices": rows, "count": total}

    def get_tariff(self, when: date) -> dict:
        rows = self.db.rows(
            "SELECT id, name, price_day_kwph, price_night_kwph, valid_from, valid_to "
            "FROM dim_tariffs FINAL WHERE toString(valid_from) <= {moment:String} "
            "AND {moment:String} < toString(valid_to) ORDER BY valid_from DESC LIMIT 1",
            moment=f"{when.isoformat()} 00:00:00",
        )
        if not rows:
            raise ApiError(404, "Not found")
        return rows[0]

    def install_gauge(self, identifier: int, gauge_id: int) -> None:
        with self.locks[identifier % len(self.locks)]:
            self.require("dim_realty", identifier)
            self.require("dim_gauges", gauge_id)
            active = self.db.rows(
                "SELECT gauge_id, realty_id, created_at, sign, version "
                "FROM fact_gauge_bindings FINAL WHERE realty_id = {id:UInt64} AND sign = 1 "
                "ORDER BY version DESC LIMIT 1", id=identifier,
            )
            rows = []
            version = 1
            if active:
                old = active[0]
                rows.append((old["gauge_id"], identifier, old["created_at"], -1, old["version"]))
                version = old["version"] + 1
            rows.append((gauge_id, identifier, self.next_timestamp(), 1, version))
            self.db.insert("fact_gauge_bindings", rows)
