"""Shared request helpers: database dependency, templates and the context every template receives."""

import sqlite3
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates

from app import db
from app.config import APP_DIR, Settings
from app.security import csrf_token, is_admin, settings_of
from app.texts import GLOBAL_KEYS, TEXTS, load_texts

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from starlette.responses import Response


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    conn = db.connect(settings_of(request).db_path)
    try:
        yield conn
    finally:
        conn.close()


DB = Annotated[sqlite3.Connection, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(settings_of)]


def _template_context(request: Request) -> dict[str, Any]:
    conn = db.connect(settings_of(request).db_path)
    try:
        values = load_texts(conn)
    finally:
        conn.close()
    return {
        "t": values,
        "TEXTS": TEXTS,
        "GLOBAL_KEYS": GLOBAL_KEYS,
        "is_admin": is_admin(request),
        "csrf_token": lambda: csrf_token(request),
    }


templates = Jinja2Templates(directory=APP_DIR / "templates", context_processors=[_template_context])


def render(
    request: Request,
    name: str,
    context: dict[str, Any] | None = None,
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
) -> Response:
    return templates.TemplateResponse(request, name, context or {}, status_code=status_code, headers=headers)
