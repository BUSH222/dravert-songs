"""Administrator: login, songs, photos and editable texts."""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from mutagen import MutagenError
from mutagen.id3 import ID3, TDRC, TIT2, TPE1, ID3NoHeaderError
from mutagen.mp3 import MP3

from app import db
from app.security import (
    check_credentials,
    client_ip,
    csrf_valid,
    is_admin,
    log_in,
    log_out,
    require_admin,
    safe_next,
    verify_csrf,
)
from app.texts import TEXTS
from app.web import DB, AppSettings, render

if TYPE_CHECKING:
    import sqlite3

# Login and logout are reachable without a session; everything else requires the admin.
auth_router = APIRouter(prefix="/admin")
router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])

CSRF = [Depends(verify_csrf)]
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}

AUTHOR = "P.L. Dravert"
# Frames removed from every stored MP3: comments, pictures, other artist roles and the dates other than the year.
STRIPPED_FRAMES = ("COMM", "APIC", "TPE2", "TPE3", "TPE4", "TYER", "TDAT", "TIME", "TRDA", "TORY", "TDOR", "TDRL")

FormStr = Annotated[str, Form()]
NextUrl = Annotated[str, Form(alias="next")]


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


# ----- login -------------------------------------------------------------------------------------


@auth_router.get("/login", name="admin_login")
def login_form(request: Request, next_url: Annotated[str | None, Query(alias="next")] = None) -> Response:
    if is_admin(request):
        return _redirect(safe_next(next_url, str(request.url_for("admin_songs"))))
    return render(request, "login.html", {"error": None, "username": None, "next": next_url})


@auth_router.post("/login", name="admin_login_submit")
def login_submit(
    request: Request,
    username: FormStr = "",
    password: FormStr = "",
    csrf_token: FormStr = "",
    next_url: NextUrl = "",
) -> Response:
    def fail(error: str, status_code: int, headers: dict[str, str] | None = None) -> Response:
        ctx = {"error": error, "username": username, "next": next_url}
        return render(request, "login.html", ctx, status_code=status_code, headers=headers)

    throttle = request.app.state.login_throttle
    ip = client_ip(request)
    wait = throttle.check(ip)
    if wait:
        return fail(f"Слишком много попыток входа. Повторите через {wait} с.", 429, {"Retry-After": str(wait)})
    if not csrf_valid(request, csrf_token):
        return fail("Сессия устарела. Попробуйте ещё раз.", 400)
    if not check_credentials(request.app.state.settings, username, password):
        throttle.failure(ip)
        return fail("Неверное имя пользователя или пароль", 401)
    throttle.success(ip)
    log_in(request)
    return _redirect(safe_next(next_url, str(request.url_for("admin_songs"))))


@auth_router.post("/logout", name="admin_logout", dependencies=CSRF)
def logout(request: Request) -> Response:
    log_out(request)
    return _redirect(str(request.url_for("start")))


@router.get("", name="admin_home")
def admin_home(request: Request) -> Response:
    return _redirect(str(request.url_for("admin_songs")))


# ----- songs -------------------------------------------------------------------------------------


@dataclass
class SongForm:
    """Raw form values, kept as strings so a form with errors can be shown again as typed."""

    title: str = ""
    year: str = ""
    genre: str = ""
    description: str = ""
    epigraph: str = ""
    lyrics: str = ""
    comments: str = ""
    listens: str = "0"

    @classmethod
    def from_song(cls, song: db.Song) -> SongForm:
        return cls(
            title=song.title,
            year=str(song.year),
            genre=song.genre or "",
            description=song.description,
            epigraph=song.epigraph or "",
            lyrics=song.lyrics,
            comments=song.comments or "",
            listens=str(song.listens),
        )

    def validate(self) -> tuple[db.SongFields | None, int, dict[str, str]]:
        errors: dict[str, str] = {}

        def text(value: str) -> str:
            return value.replace("\r\n", "\n").strip()

        title = " ".join(self.title.split())
        if not title:
            errors["title"] = "Укажите название."
        try:
            year = int(self.year)
        except ValueError:
            year = 0
        if not db.MIN_YEAR <= year <= db.MAX_YEAR:
            errors["year"] = f"Год стихотворения должен быть от {db.MIN_YEAR} до {db.MAX_YEAR}."
        try:
            listens = int(self.listens or 0)
        except ValueError:
            listens = -1
        if listens < 0:
            errors["listens"] = "Число прослушиваний должно быть целым и не меньше нуля."
        if errors:
            return None, 0, errors
        fields = db.SongFields(
            title=title,
            year=year,
            genre=" ".join(self.genre.split()) or None,
            description=text(self.description),
            epigraph=text(self.epigraph) or None,
            lyrics=text(self.lyrics),
            comments=text(self.comments) or None,
        )
        return fields, listens, errors


def song_form(
    title: FormStr = "",
    year: FormStr = "",
    genre: FormStr = "",
    description: FormStr = "",
    epigraph: FormStr = "",
    lyrics: FormStr = "",
    comments: FormStr = "",
    listens: FormStr = "0",
) -> SongForm:
    return SongForm(title, year, genre, description, epigraph, lyrics, comments, listens)


SongFormData = Annotated[SongForm, Depends(song_form)]
AudioUpload = Annotated[UploadFile | None, File()]


def _uploaded(file: UploadFile | None) -> UploadFile | None:
    """Browsers send an empty part when no file was chosen."""
    return file if file is not None and file.filename else None


def _clean_tags(path: Path, title: str, year: int) -> None:
    """Rewrite the ID3 tag: only our title, author and year; no comments, pictures or other artists."""
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    for frame in STRIPPED_FRAMES:
        tags.delall(frame)
    tags.setall("TIT2", [TIT2(encoding=3, text=title)])
    tags.setall("TPE1", [TPE1(encoding=3, text=AUTHOR)])
    tags.setall("TDRC", [TDRC(encoding=3, text=str(year))])
    tags.save(path, v1=0)  # v1=0 also drops the legacy ID3v1 block, which has its own artist and comment


def _store_audio(upload: UploadFile, audio_dir: Path, title: str, year: int) -> tuple[str, int]:
    """Save an uploaded MP3 and return (file name, duration in seconds). Raises ValueError if it is not an MP3."""
    audio_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid4().hex}.mp3"
    path = audio_dir / name
    with path.open("wb") as out:
        shutil.copyfileobj(upload.file, out, 1024 * 1024)
    try:
        info = MP3(path).info
    except MutagenError:
        info = None
    if info is None:
        path.unlink(missing_ok=True)
        raise ValueError("Не удалось прочитать файл. Загрузите запись в формате MP3.")
    _clean_tags(path, title, year)
    return name, round(info.length)


def _remove(directory: Path, name: str | None) -> None:
    if name:
        (directory / name).unlink(missing_ok=True)


def _render_song_form(
    request: Request,
    conn: sqlite3.Connection,
    form: SongForm,
    song: db.Song | None,
    errors: dict[str, str] | None = None,
    saved: bool = False,
) -> Response:
    ctx: dict[str, object] = {"form": form, "song": song, "errors": errors or {}, "saved": saved}
    ctx |= {"genres": db.genres(conn), "min_year": db.MIN_YEAR, "max_year": db.MAX_YEAR}
    return render(request, "admin/song_form.html", ctx, status_code=400 if errors else 200)


@router.get("/songs", name="admin_songs")
def songs_list(request: Request, conn: DB) -> Response:
    songs = db.all_songs(conn)
    groups = [(decade, [s for s in songs if s.decade == decade]) for decade in db.DECADES]
    return render(request, "admin/songs.html", {"groups": groups, "total": len(songs)})


@router.get("/songs/new", name="admin_song_new")
def song_new(request: Request, conn: DB, year: int | None = None) -> Response:
    return _render_song_form(request, conn, SongForm(year=str(year) if year else ""), None)


@router.post("/songs/new", name="admin_song_create", dependencies=CSRF)
def song_create(
    request: Request, conn: DB, settings: AppSettings, form: SongFormData, audio: AudioUpload = None
) -> Response:
    fields, listens, errors = form.validate()
    if fields is None:
        return _render_song_form(request, conn, form, None, errors)
    stored = None
    if upload := _uploaded(audio):
        try:
            stored = _store_audio(upload, settings.audio_dir, fields.title, fields.year)
        except ValueError as e:
            return _render_song_form(request, conn, form, None, {"audio": str(e)})
    with db.transaction(conn):
        song_id = db.create_song(conn, fields)
        db.set_song_listens(conn, song_id, listens)
        if stored:
            db.set_song_audio(conn, song_id, *stored)
    return _redirect(str(request.url_for("admin_song_edit", song_id=song_id)) + "?saved=1")


def _get_song(conn: sqlite3.Connection, song_id: int) -> db.Song:
    song = db.get_song(conn, song_id)
    if song is None:
        raise HTTPException(404)
    return song


@router.get("/songs/{song_id}", name="admin_song_edit")
def song_edit(request: Request, conn: DB, song_id: int, saved: bool = False) -> Response:
    song = _get_song(conn, song_id)
    return _render_song_form(request, conn, SongForm.from_song(song), song, saved=saved)


@router.post("/songs/{song_id}", name="admin_song_update", dependencies=CSRF)
def song_update(
    request: Request,
    conn: DB,
    settings: AppSettings,
    song_id: int,
    form: SongFormData,
    audio: AudioUpload = None,
) -> Response:
    song = _get_song(conn, song_id)
    fields, listens, errors = form.validate()
    if fields is None:
        return _render_song_form(request, conn, form, song, errors)
    stored = None
    if upload := _uploaded(audio):
        try:
            stored = _store_audio(upload, settings.audio_dir, fields.title, fields.year)
        except ValueError as e:
            return _render_song_form(request, conn, form, song, {"audio": str(e)})
    elif song.audio_file:  # the title or year may have changed, so refresh the tags of the kept recording
        _clean_tags(settings.audio_dir / song.audio_file, fields.title, fields.year)
    with db.transaction(conn):
        db.update_song(conn, song_id, fields)
        db.set_song_listens(conn, song_id, listens)
        if stored:
            db.set_song_audio(conn, song_id, *stored)
    if stored:
        _remove(settings.audio_dir, song.audio_file)
    return _redirect(str(request.url_for("admin_song_edit", song_id=song_id)) + "?saved=1")


@router.post("/songs/{song_id}/delete", name="admin_song_delete", dependencies=CSRF)
def song_delete(request: Request, conn: DB, settings: AppSettings, song_id: int) -> Response:
    song = _get_song(conn, song_id)
    db.delete_song(conn, song_id)
    _remove(settings.audio_dir, song.audio_file)
    return _redirect(str(request.url_for("admin_songs")))


# ----- photos ------------------------------------------------------------------------------------


@router.get("/photos", name="admin_photos")
def photos_page(request: Request, conn: DB) -> Response:
    return render(request, "admin/photos.html", _photos_ctx(request, conn, None))


@router.post("/photos", name="admin_photos_upload", dependencies=CSRF)
def photos_upload(
    request: Request,
    conn: DB,
    settings: AppSettings,
    files: Annotated[list[UploadFile], File()],
    alt: FormStr = "",
) -> Response:
    uploads = [f for f in files if f.filename]
    rejected = [f.filename for f in uploads if Path(f.filename or "").suffix.lower() not in PHOTO_EXTENSIONS]
    if rejected:
        msg = f"Неподдерживаемый формат: {', '.join(n or '' for n in rejected)}. Можно: JPG, PNG, WebP, GIF, AVIF."
        return render(request, "admin/photos.html", _photos_ctx(request, conn, msg), status_code=400)
    settings.photos_dir.mkdir(parents=True, exist_ok=True)
    for upload in uploads:
        name = f"{uuid4().hex}{Path(upload.filename or '').suffix.lower()}"
        with (settings.photos_dir / name).open("wb") as out:
            shutil.copyfileobj(upload.file, out, 1024 * 1024)
        db.add_photo(conn, name, " ".join(alt.split()))
    return _redirect(str(request.url_for("admin_photos")))


def _photos_ctx(request: Request, conn: sqlite3.Connection, error: str | None) -> dict[str, object]:
    photos = [{"photo": p, "url": request.url_for("photos", path=p.filename)} for p in db.all_photos(conn)]
    return {"photos": photos, "error": error}


@router.post("/photos/{photo_id}", name="admin_photo_update", dependencies=CSRF)
def photo_update(request: Request, conn: DB, photo_id: int, alt: FormStr = "") -> Response:
    db.set_photo_alt(conn, photo_id, " ".join(alt.split()))
    return _redirect(str(request.url_for("admin_photos")))


@router.post("/photos/{photo_id}/move", name="admin_photo_move", dependencies=CSRF)
def photo_move(request: Request, conn: DB, photo_id: int, direction: FormStr = "") -> Response:
    db.move_photo(conn, photo_id, -1 if direction == "up" else 1)
    return _redirect(str(request.url_for("admin_photos")))


@router.post("/photos/{photo_id}/delete", name="admin_photo_delete", dependencies=CSRF)
def photo_delete(request: Request, conn: DB, settings: AppSettings, photo_id: int) -> Response:
    photo = db.get_photo(conn, photo_id)
    if photo:
        db.delete_photo(conn, photo_id)
        _remove(settings.photos_dir, photo.filename)
    return _redirect(str(request.url_for("admin_photos")))


# ----- texts -------------------------------------------------------------------------------------


@router.post("/texts", name="admin_text_update", dependencies=CSRF)
def text_update(
    request: Request,
    conn: DB,
    key: FormStr,
    value: FormStr = "",
    restore_default: FormStr = "",
    next_url: NextUrl = "",
) -> Response:
    field = TEXTS.get(key)
    if field is None:
        raise HTTPException(400, "Неизвестный текст")
    if restore_default:
        db.reset_text(conn, key)
    else:
        value = value.replace("\r\n", "\n")
        db.set_text(conn, key, " ".join(value.split()) if field.kind == "line" else value.strip())
    return _redirect(safe_next(next_url, str(request.url_for("start"))))
