"""HTTP API of the Energosbyt service."""

import logging
import re
from contextlib import asynccontextmanager
from datetime import date, datetime

from clickhouse_connect.driver.exceptions import ClickHouseError
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.config import Settings
from app.database import Database
from app.models import GaugeInstall, ReadingCreate, UserPatch, parse_date
from app.service import ApiError, Service

logger = logging.getLogger(__name__)


def present(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: present(item) for key, item in value.items()}
    if isinstance(value, list):
        return [present(item) for item in value]
    return value


def integer_parameter(value: str, name: str, maximum: int | None = None) -> int:
    try:
        if not re.fullmatch(r"[0-9]+", value):
            raise ValueError
        number = int(value)
        if maximum is not None and number > maximum:
            raise ValueError
        return number
    except (ValueError, TypeError):
        raise ApiError(400, f'invalid "{name}" parameter') from None


def date_parameter(value: str | None, name: str) -> date:
    try:
        return parse_date(value)
    except (ValueError, TypeError):
        raise ApiError(400, f'invalid "{name}" parameter') from None


def identifier(value: str) -> int:
    return integer_parameter(value, "id", 2**64 - 1)


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = Settings.from_environment()
    database = Database(settings)
    application.state.service = Service(database, "UTC")
    try:
        yield
    finally:
        database.close()


app = FastAPI(title="ЭнергоСбыт API", version="1.0.0", lifespan=lifespan)


@app.exception_handler(ApiError)
async def api_error(_request: Request, error: ApiError):
    return JSONResponse({"message": error.message}, status_code=error.status)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, error: RequestValidationError):
    first = error.errors()[0]
    location = first["loc"]
    if location and location[0] == "body":
        field = str(location[1]) if len(location) > 1 and isinstance(location[1], str) else "body"
        match = re.search(r'invalid "(fio|phone)" field', first["msg"])
        if match:
            field = match[1]
        message = f'invalid "{field}" field'
    else:
        field = str(location[-1]) if location else "request"
        message = f'invalid "{field}" parameter'
    return JSONResponse({"message": message}, status_code=400)


@app.exception_handler(HTTPException)
async def http_error(_request: Request, error: HTTPException):
    message = "Not found" if error.status_code == 404 else str(error.detail)
    return JSONResponse({"message": message}, status_code=error.status_code)


@app.exception_handler(ClickHouseError)
async def database_error(_request: Request, error: ClickHouseError):
    logger.error("ClickHouse request failed: %s", error)
    return JSONResponse({"message": "Database unavailable"}, status_code=503)


def empty(status: int) -> Response:
    return Response(status_code=status, headers={"Content-Length": "0"})


@app.get("/ping")
def ping():
    return empty(200)


@app.get("/users/{id}")
def get_user(id: str, request: Request):
    return request.app.state.service.get_user(identifier(id))


@app.patch("/users/{id}", status_code=204)
def patch_user(id: str, patch: UserPatch, request: Request):
    request.app.state.service.patch_user(identifier(id), patch)
    return empty(204)


@app.get("/realty/{id}")
def get_realty(id: str, request: Request):
    return request.app.state.service.get_realty(identifier(id))


@app.post("/realty/{id}/readings", status_code=201)
def add_reading(id: str, reading: ReadingCreate, request: Request):
    if not date(1970, 1, 1) <= reading.reading_date <= date(2149, 6, 6):
        raise ApiError(400, 'invalid "reading_date" field')
    request.app.state.service.add_reading(identifier(id), reading)
    return empty(201)


@app.get("/realty/{id}/readings")
def list_readings(id: str, request: Request, date_from: str | None = None, date_to: str | None = None):
    start, end = date_parameter(date_from, "date_from"), date_parameter(date_to, "date_to")
    if start > end:
        raise ApiError(400, 'invalid "date_from" parameter')
    return present(request.app.state.service.list_readings(identifier(id), start, end))


@app.get("/realty/{id}/invoices")
def list_invoices(id: str, request: Request, limit: str = "10", offset: str = "0"):
    limit_value = integer_parameter(limit, "limit")
    offset_value = integer_parameter(offset, "offset")
    return present(request.app.state.service.list_invoices(identifier(id), limit_value, offset_value))


@app.get("/tariffs")
def get_tariff(request: Request, date: str | None = None):
    return present(request.app.state.service.get_tariff(date_parameter(date, "date")))


@app.post("/realty/{id}/gauges", status_code=201)
def install_gauge(id: str, gauge: GaugeInstall, request: Request):
    request.app.state.service.install_gauge(identifier(id), gauge.gauge_id)
    return empty(201)
