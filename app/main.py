"""Application factory."""

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app import db
from app.config import APP_DIR, Settings
from app.routes import admin, public
from app.security import AdminRequired, LoginThrottle
from app.web import render

ERROR_TITLES = {
    403: "Доступ запрещён",
    404: "Страница не найдена",
    405: "Метод не поддерживается",
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    db.init_db(settings.db_path)
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    settings.photos_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.login_throttle = LoginThrottle()

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="dr_session",
        max_age=settings.session_max_age,
        same_site="lax",
        https_only=settings.secure_cookies,
    )

    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
    app.mount("/media/photos", StaticFiles(directory=settings.photos_dir), name="photos")
    app.include_router(public.router)
    app.include_router(admin.auth_router)
    app.include_router(admin.router)

    @app.exception_handler(AdminRequired)
    def to_login(request: Request, _: AdminRequired) -> Response:
        url = request.url_for("admin_login")
        if request.method == "GET":
            target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
            url = url.include_query_params(next=target)
        return RedirectResponse(url, status_code=303)

    @app.exception_handler(StarletteHTTPException)
    async def html_errors(request: Request, exc: StarletteHTTPException) -> Response:
        if request.url.path.startswith(("/api/", "/audio/", "/static/", "/media/")):
            return await http_exception_handler(request, exc)
        title = ERROR_TITLES.get(exc.status_code, "Ошибка")
        detail = exc.detail if isinstance(exc.detail, str) and exc.detail != title else None
        ctx = {"status": exc.status_code, "title": title, "detail": detail}
        return render(request, "error.html", ctx, status_code=exc.status_code, headers=exc.headers)

    return app
