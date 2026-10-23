"""Public pages, audio files and the listen counter."""

import re
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from app import db
from app.security import ip_hash
from app.web import DB, AppSettings, render

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

    from app.config import Settings

router = APIRouter()

LISTEN_WINDOW = 3600  # a browser / IP counts at most once per song per hour


def _check_decade(decade: int) -> None:
    if decade not in db.DECADES:
        raise HTTPException(404)


def _collate(title: str) -> str:
    """Sort key: ignore leading quotes and punctuation, treat Ё as Е."""
    return re.sub(r"^\W+", "", title).casefold().replace("ё", "е")


def _first_letter(title: str) -> str:
    letter = next((ch.upper() for ch in title if ch.isalpha()), "#")
    return "Е" if letter == "Ё" else letter


def _letter_order(letter: str) -> tuple[int, str]:
    # Cyrillic first, then other alphabets, then titles without letters.
    if "А" <= letter <= "Я":
        return 0, letter
    return (1 if letter.isalpha() else 2), letter


@router.get("/", name="start")
def start(request: Request, conn: DB) -> Response:
    photos = [
        {"url": request.url_for("photos", path=p.filename), "alt": p.alt or "Архивная фотография"}
        for p in db.all_photos(conn)
    ]
    return render(request, "start.html", {"photos": photos})


@router.get("/decades/{decade}", name="decade")
def decade_page(request: Request, decade: int, conn: DB) -> Response:
    """Redirect to the first song of the decade, or show the empty state."""
    _check_decade(decade)
    songs = db.decade_songs(conn, decade)
    if songs:
        return RedirectResponse(request.url_for("song", decade=decade, song_id=songs[0].id), status_code=302)
    return render(request, "decade.html", {"decade": decade, "songs": [], "song": None})


@router.get("/decades/{decade}/songs/{song_id}", name="song")
def song_page(request: Request, decade: int, song_id: int, conn: DB) -> Response:
    _check_decade(decade)
    song = db.get_song(conn, song_id)
    if song is None:
        raise HTTPException(404)
    if song.decade != decade:  # the poem year was edited: send old links to the right decade
        return RedirectResponse(request.url_for("song", decade=song.decade, song_id=song.id), status_code=302)
    ctx = {"decade": decade, "songs": db.decade_songs(conn, decade), "song": song}
    return render(request, "decade.html", ctx)


@router.get("/catalog", name="catalog")
def catalog(request: Request, conn: DB, sort: str = "alpha") -> Response:
    mode = "rating" if sort == "rating" else "alpha"
    songs = db.all_songs(conn)
    ctx: dict[str, object] = {"mode": mode, "has_songs": bool(songs)}
    if mode == "alpha":
        by_letter: dict[str, list[db.Song]] = {}
        for song in sorted(songs, key=lambda s: _collate(s.title)):
            by_letter.setdefault(_first_letter(song.title), []).append(song)
        letters = sorted(by_letter, key=_letter_order)
        ctx |= {"groups": [{"letter": k, "songs": by_letter[k]} for k in letters], "letters": letters}
    else:
        ctx["ranked"] = sorted(songs, key=lambda s: (-s.listens, _collate(s.title)))
    return render(request, "catalog.html", ctx)


# ----- audio -------------------------------------------------------------------------------------


def _audio(conn: sqlite3.Connection, settings: Settings, song_id: int) -> tuple[db.Song, Path]:
    song = db.get_song(conn, song_id)
    if song is None or not song.audio_file:
        raise HTTPException(404)
    path = settings.audio_dir / song.audio_file
    if not path.is_file():
        raise HTTPException(404)
    return song, path


@router.get("/audio/{song_id}", name="audio")
def audio(song_id: int, conn: DB, settings: AppSettings) -> FileResponse:
    # FileResponse answers Range requests with 206 Partial Content (needed for seeking and iOS Safari).
    _, path = _audio(conn, settings, song_id)
    return FileResponse(path, media_type="audio/mpeg")


@router.get("/audio/{song_id}/download", name="audio_download")
def audio_download(song_id: int, conn: DB, settings: AppSettings) -> FileResponse:
    song, path = _audio(conn, settings, song_id)
    return FileResponse(path, media_type="audio/mpeg", filename=song.download_name)


@router.post("/api/songs/{song_id}/started", name="song_started", status_code=204)
def song_started(request: Request, song_id: int, conn: DB, settings: AppSettings) -> Response:
    """Sent by the player once per page view when playback begins. Counts at most once per hour per browser and IP."""
    if db.get_song(conn, song_id) is None:
        raise HTTPException(404)
    response = Response(status_code=204)
    cookie = f"heard_{song_id}"
    if request.cookies.get(cookie):
        return response
    db.register_listen(conn, song_id, ip_hash(request), LISTEN_WINDOW)
    response.set_cookie(
        cookie, "1", max_age=LISTEN_WINDOW, httponly=True, samesite="lax", secure=settings.secure_cookies
    )
    return response
