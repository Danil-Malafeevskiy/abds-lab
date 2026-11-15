# ЭнергоСбыт

[![labs](https://github.com/Danil-Malafeevskiy/abds-lab/actions/workflows/energosbyt.lab.yml/badge.svg)](https://github.com/Danil-Malafeevskiy/abds-lab/actions/workflows/energosbyt.lab.yml)

Backend-сервис вымышленной ЖКХ-компании для практики по курсу «Архитектура систем обработки больших данных».

Стек: Python 3.12, FastAPI, ClickHouse 26.7.

## Запуск

Нужны Docker Compose, GNU Make и Python 3.12+.

```bash
make run
make setup
curl http://localhost:8080/ping
```

Настройки подключения находятся в [.env.local](.env.local).
`make run` и `make rund` создают ссылку `.env` на `.env.local`, чтобы команды
`docker compose` без `--env-file` также получали настройки.
По умолчанию API работает на порту `8080`, ClickHouse — на `8123` и `9000`,
пользователь ClickHouse — `default`, пароль пустой.

## Команды

| Команда | Действие |
| --- | --- |
| `make run` | Собрать и запустить сервисы, дождаться готовности |
| `make rund` | Запустить сервисы с выводом логов |
| `make services` | Показать состояние контейнеров |
| `make gen` | Сгенерировать CSV в `data/` |
| `make load` | Загрузить CSV в пустые таблицы |
| `make setup` | Создать схему, сгенерировать и загрузить данные |
| `make teardown` | Удалить таблицы и их данные, оставив CSV |
| `make stop` | Остановить контейнеры, сохранив данные в `volume/` |
| `make clean` | Удалить таблицы и остановить сервисы |

`setup`, `load`, `teardown` и `clean` требуют запущенного ClickHouse.
Повторная загрузка в непустые таблицы отклоняется. Для пересоздания данных
выполните `make teardown`, затем `make setup`.

## API

[Swagger](http://localhost:8080/docs) · [Коллекция Postman](api/energosbyt.postman_collection.json)

| Метод | Путь | Действие |
| --- | --- | --- |
| GET | `/ping` | Проверить доступность |
| GET | `/users/{id}` | Получить собственника |
| PATCH | `/users/{id}` | Изменить ФИО или телефон |
| GET | `/realty/{id}` | Получить объект недвижимости |
| POST | `/realty/{id}/readings` | Передать или скорректировать показание |
| GET | `/realty/{id}/readings?date_from=...&date_to=...` | Получить актуальные показания за период |
| GET | `/realty/{id}/invoices?limit=10&offset=0` | Получить счета, начиная с новых |
| GET | `/tariffs?date=YYYY-MM-DD` | Получить тариф на дату |
| POST | `/realty/{id}/gauges` | Установить или заменить счётчик |

Тела запросов и ответов — JSON, ошибки — `{"message":"..."}`.
Даты имеют формат `YYYY-MM-DD`, время — `YYYY-MM-DD HH:MM:SS` в UTC.

## Данные и схема

CSV сохраняются в `data/`, данные ClickHouse — в `volume/`; оба каталога исключены из Git.
Схема описана в [app/schema.py](app/schema.py).

| Таблица | Движок | Ключ сортировки | Строк в CSV |
| --- | --- | --- | ---: |
| `dim_realty` | `MergeTree` | `id` | 1 000 |
| `dim_gauges` | `MergeTree` | `id` | 1 100 |
| `dim_users` | `ReplacingMergeTree(updated_at)` | `id` | 1 000 |
| `dim_tariffs` | `ReplacingMergeTree(updated_at)` | `(id, valid_from)` | 2 |
| `fact_gauge_bindings` | `VersionedCollapsingMergeTree(sign, version)` | `(realty_id, gauge_id)` | 1 200 |
| `fact_meter_readings` | `ReplacingMergeTree(created_at)` | `(realty_id, reading_date)` | 1 128 880 |
| `fact_invoice` | `MergeTree` | `(realty_id, created_at)` | 36 000 |

Генератор использует seed `42` и период `2023-11-01` — `2026-10-31`.
Для 3% показаний создаются корректировки, для 100 объектов — замены счётчиков.
После `FINAL` остаются 1 096 000 показаний и 1 000 активных установок.
Счета рассчитываются по месячному потреблению и версии тарифа на дату счёта.
Суммы хранятся в копейках, срок оплаты — 10-е число следующего месяца.

Ключ `id` используется для поиска измерений; `valid_from` сохраняет историю тарифа.
Ключ показаний объединяет все корректировки одной даты, ключ установок — счётчик и объект.
Показания и счета разбиты по месяцам `reading_date` и `created_at`: это соответствует
запросам за период. Измерения небольшие и не разделяются на партиции; установки также
не разделяются, чтобы исходная строка и её отмена могли схлопнуться.

## Проверка SCD и удаления

Изменения собственника, показаний и счётчика выполняются запросами из Postman.
Для SQL с настройками по умолчанию откройте клиент:

```bash
docker compose --env-file .env.local exec clickhouse clickhouse-client --database energosbyt --multiquery
```

Запросы ниже рассчитаны на сгенерированные данные.

```sql
-- SCD 1: после PATCH fio возвращается новое ФИО, старого нет даже без FINAL.
SELECT fio FROM dim_users FINAL WHERE id = 1;
SELECT count() FROM dim_users
WHERE id = 1 AND fio = 'Иванов Иван Собственникович 1';

-- SCD 3: после двух смен телефона видны текущий и предыдущий номера.
SELECT phone, phone_prev FROM dim_users FINAL WHERE id = 1;

-- SCD 2: две версии тарифа с границей 2025-11-01.
SELECT price_day_kwph, price_night_kwph, valid_from, valid_to
FROM dim_tariffs FINAL WHERE id = 1 ORDER BY valid_from;

-- Пересчёт старого счёта: сохранённая сумма совпадает с расчётом по историческому тарифу.
SELECT i.price AS stored_price,
       toUInt64(i.day_kw) * t.price_day_kwph
         + toUInt64(i.night_kw) * t.price_night_kwph AS recalculated_price
FROM fact_invoice AS i INNER JOIN dim_tariffs AS t FINAL ON i.tariff_id = t.id
WHERE i.realty_id = 1 AND i.created_at >= '2025-10-01 00:00:00'
  AND i.created_at < '2025-11-01 00:00:00'
  AND t.valid_from <= i.created_at AND i.created_at < t.valid_to;

-- После повторного POST показания за дату возвращается одна актуальная строка.
SELECT day_kw, night_kw FROM fact_meter_readings FINAL
WHERE realty_id = 1 AND reading_date = '2026-10-01';

-- После POST установки остаётся активный счётчик с новой версией.
SELECT gauge_id, sign, version FROM fact_gauge_bindings FINAL WHERE realty_id = 1;

-- Ошибочный счёт: вставка, удаление и проверка, что строк больше нет (count = 0).
INSERT INTO fact_invoice VALUES
(1, 1, 1, 1001, 10, 5, 930000, '2027-01-10', '2026-12-31 23:00:00');
ALTER TABLE fact_invoice DELETE
WHERE realty_id = 1 AND created_at = '2026-12-31 23:00:00' AND price = 930000
SETTINGS mutations_sync = 1;
SELECT count() FROM fact_invoice
WHERE realty_id = 1 AND created_at = '2026-12-31 23:00:00' AND price = 930000;
```

Правила работы с репозиторием: [CONTRIBUTING.md](CONTRIBUTING.md).
