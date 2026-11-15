"""Deterministic, bounded-memory generation of sample energy usage data."""

import calendar
import csv
import random
from contextlib import ExitStack
from datetime import date, timedelta
from pathlib import Path

from app.schema import TABLES

START = date(2023, 11, 1)
END = date(2026, 10, 31)
TARIFF_CHANGE = date(2025, 11, 1)
REPLACEMENT = date(2025, 7, 1)
REALTY_COUNT = 1000
REPLACEMENT_COUNT = 100
CREATED = "2023-10-31 00:00:00"


def generate(directory: Path, seed: int) -> dict[str, int]:
    directory.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    dates = [START + timedelta(days=i) for i in range((END - START).days + 1)]
    total = REALTY_COUNT * len(dates)
    corrected = set(rng.sample(range(total), total * 3 // 100))
    counts = dict.fromkeys(TABLES, 0)

    with ExitStack() as stack:
        writers = {
            table: csv.writer(stack.enter_context(
                (directory / f"{table}.csv").open("w", encoding="utf-8", newline=""),
            ), lineterminator="\n")
            for table in TABLES
        }

        def write(table: str, row: tuple | list) -> None:
            writers[table].writerow(row)
            counts[table] += 1

        write("dim_tariffs", (1, "День–Ночь", 500, 250, f"{START} 00:00:00",
                              f"{TARIFF_CHANGE} 00:00:00", CREATED, CREATED))
        write("dim_tariffs", (1, "День–Ночь", 620, 310, f"{TARIFF_CHANGE} 00:00:00",
                              "2099-01-01 00:00:00", f"{TARIFF_CHANGE} 00:00:00",
                              f"{TARIFF_CHANGE} 00:00:00"))

        for identifier in range(1, REALTY_COUNT + 1):
            commercial = identifier % 10 == 0
            number = (identifier - 1) % 100 + 1
            write("dim_realty", (
                identifier, f"г. Москва, ул. Энергетиков, д. {(identifier - 1) // 100 + 1}",
                rng.randint(30, 150), "nrcp" if commercial else "flat",
                "" if commercial else str(number), 0 if commercial else rng.randint(1, 4),
                (number - 1) // 10 + 1, (number - 1) // 50 + 1, CREATED,
            ))
            write("dim_users", (identifier, f"Иванов Иван Собственникович {identifier}",
                                f"+7900{identifier:07d}", "", CREATED, CREATED))
            write("dim_gauges", (identifier, "Меркурий 200.02", "Россия", CREATED))
            original = (identifier, identifier, CREATED, 1, 1)
            write("fact_gauge_bindings", original)
            if identifier <= REPLACEMENT_COUNT:
                write("dim_gauges", (REALTY_COUNT + identifier, "Энергомера CE102", "Россия",
                                     f"{REPLACEMENT} 00:00:00"))
                write("fact_gauge_bindings", (*original[:3], -1, 1))
                write("fact_gauge_bindings", (REALTY_COUNT + identifier, identifier,
                                             f"{REPLACEMENT} 00:00:00", 1, 2))

            day_total = night_total = 0
            month_day = month_night = 0
            gauge = identifier
            for day_index, reading_date in enumerate(dates):
                if identifier <= REPLACEMENT_COUNT and reading_date == REPLACEMENT:
                    gauge = REALTY_COUNT + identifier
                    day_total = night_total = 0
                daily_day, daily_night = rng.randint(5, 15), rng.randint(1, 5)
                day_total += daily_day
                night_total += daily_night
                month_day += daily_day
                month_night += daily_night
                key = (identifier, identifier, 1, gauge, reading_date.isoformat())
                if (identifier - 1) * len(dates) + day_index in corrected:
                    write("fact_meter_readings", (*key, day_total + 1, night_total + 1,
                                                  f"{reading_date} 12:00:00"))
                write("fact_meter_readings", (*key, day_total, night_total,
                                              f"{reading_date} 12:00:01"))

                if reading_date.day == calendar.monthrange(reading_date.year, reading_date.month)[1]:
                    next_month = reading_date + timedelta(days=1)
                    day_price, night_price = (500, 250) if reading_date < TARIFF_CHANGE else (620, 310)
                    write("fact_invoice", (
                        identifier, identifier, 1, gauge, month_day, month_night,
                        month_day * day_price + month_night * night_price,
                        next_month.replace(day=10).isoformat(), f"{reading_date} 23:00:00",
                    ))
                    month_day = month_night = 0
    return counts
