"""SQLite storage: connection helpers, schema and all queries."""

import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

# The decade categories are fixed. A song belongs to the decade of its poem year.
DECADES = (1900, 1910, 1920, 1930, 1940)
MIN_YEAR, MAX_YEAR = DECADES[0], DECADES[-1] + 9

SCHEMA = """
CREATE TABLE IF NOT EXISTS songs (
    id          INTEGER PRIMARY KEY,
    title       TEXT    NOT NULL,
    poem_year   INTEGER NOT NULL,
    genre       TEXT,
    description TEXT    NOT NULL DEFAULT '',  -- trusted HTML
    epigraph    TEXT,
    lyrics      TEXT    NOT NULL DEFAULT '',  -- stanzas separated by a blank line
    comments    TEXT,                         -- trusted HTML
    audio_file  TEXT,                         -- file name inside DATA_DIR/audio
    duration    INTEGER NOT NULL DEFAULT 0,   -- seconds
    listens     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS listens (
    song_id  INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    ip_hash  TEXT    NOT NULL,
    heard_at REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS listens_song_ip ON listens (song_id, ip_hash);
CREATE INDEX IF NOT EXISTS listens_heard_at ON listens (heard_at);

CREATE TABLE IF NOT EXISTS photos (
    id       INTEGER PRIMARY KEY,
    filename TEXT    NOT NULL,
    alt      TEXT    NOT NULL DEFAULT '',
    position INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS texts (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    # One connection per request. FastAPI may run a dependency and its endpoint in different threads.
    conn = sqlite3.connect(path, autocommit=True, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


# ----- songs -------------------------------------------------------------------------------------


@dataclass
class Song:
    id: int
    title: str
    year: int
    genre: str | None
    description: str
    epigraph: str | None
    lyrics: str
    comments: str | None
    audio_file: str | None
    duration: int
    listens: int

    @property
    def decade(self) -> int:
        return self.year // 10 * 10

    @property
    def stanzas(self) -> list[list[str]]:
        blocks = re.split(r"\n[ \t]*\n", self.lyrics.strip())
        return [[line.rstrip() for line in block.splitlines()] for block in blocks if block.strip()]

    @property
    def download_name(self) -> str:
        name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "", self.title).strip(" .") or f"song-{self.id}"
        return f"{name}.mp3"


@dataclass
class SongFields:
    """Everything the admin form edits (the audio file is handled separately)."""

    title: str
    year: int
    genre: str | None
    description: str
    epigraph: str | None
    lyrics: str
    comments: str | None


_SONG_COLUMNS = (
    "id, title, poem_year AS year, genre, description, epigraph, lyrics, comments, audio_file, duration, listens"
)
_SONG_ORDER = "ORDER BY poem_year, title COLLATE NOCASE, id"


def _song(row: sqlite3.Row) -> Song:
    return Song(**dict(row))


def all_songs(conn: sqlite3.Connection) -> list[Song]:
    return [_song(r) for r in conn.execute(f"SELECT {_SONG_COLUMNS} FROM songs {_SONG_ORDER}")]


def decade_songs(conn: sqlite3.Connection, decade: int) -> list[Song]:
    rows = conn.execute(
        f"SELECT {_SONG_COLUMNS} FROM songs WHERE poem_year BETWEEN ? AND ? {_SONG_ORDER}", (decade, decade + 9)
    )
    return [_song(r) for r in rows]


def get_song(conn: sqlite3.Connection, song_id: int) -> Song | None:
    row = conn.execute(f"SELECT {_SONG_COLUMNS} FROM songs WHERE id = ?", (song_id,)).fetchone()
    return _song(row) if row else None


def genres(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT DISTINCT genre FROM songs WHERE genre IS NOT NULL ORDER BY genre COLLATE NOCASE")
    return [r[0] for r in rows]


def create_song(conn: sqlite3.Connection, f: SongFields) -> int:
    cur = conn.execute(
        "INSERT INTO songs (title, poem_year, genre, description, epigraph, lyrics, comments)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (f.title, f.year, f.genre, f.description, f.epigraph, f.lyrics, f.comments),
    )
    assert cur.lastrowid is not None
    return cur.lastrowid


def update_song(conn: sqlite3.Connection, song_id: int, f: SongFields) -> None:
    conn.execute(
        "UPDATE songs SET title = ?, poem_year = ?, genre = ?, description = ?, epigraph = ?, lyrics = ?,"
        " comments = ? WHERE id = ?",
        (f.title, f.year, f.genre, f.description, f.epigraph, f.lyrics, f.comments, song_id),
    )


def set_song_audio(conn: sqlite3.Connection, song_id: int, audio_file: str, duration: int) -> None:
    conn.execute("UPDATE songs SET audio_file = ?, duration = ? WHERE id = ?", (audio_file, duration, song_id))


def set_song_listens(conn: sqlite3.Connection, song_id: int, listens: int) -> None:
    conn.execute("UPDATE songs SET listens = ? WHERE id = ?", (listens, song_id))


def delete_song(conn: sqlite3.Connection, song_id: int) -> None:
    conn.execute("DELETE FROM songs WHERE id = ?", (song_id,))


def register_listen(conn: sqlite3.Connection, song_id: int, ip_hash: str, window: int) -> bool:
    """Count a listen unless this IP was already counted for this song within `window` seconds."""
    now = time.time()
    with transaction(conn):
        conn.execute("DELETE FROM listens WHERE heard_at < ?", (now - window,))
        seen = conn.execute("SELECT 1 FROM listens WHERE song_id = ? AND ip_hash = ?", (song_id, ip_hash))
        if seen.fetchone():
            return False
        conn.execute("INSERT INTO listens (song_id, ip_hash, heard_at) VALUES (?, ?, ?)", (song_id, ip_hash, now))
        conn.execute("UPDATE songs SET listens = listens + 1 WHERE id = ?", (song_id,))
    return True


# ----- photos ------------------------------------------------------------------------------------


@dataclass
class Photo:
    id: int
    filename: str
    alt: str
    position: int


def all_photos(conn: sqlite3.Connection) -> list[Photo]:
    return [Photo(**dict(r)) for r in conn.execute("SELECT * FROM photos ORDER BY position, id")]


def get_photo(conn: sqlite3.Connection, photo_id: int) -> Photo | None:
    row = conn.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    return Photo(**dict(row)) if row else None


def add_photo(conn: sqlite3.Connection, filename: str, alt: str) -> None:
    with transaction(conn):
        (last,) = conn.execute("SELECT COALESCE(MAX(position), 0) FROM photos").fetchone()
        conn.execute("INSERT INTO photos (filename, alt, position) VALUES (?, ?, ?)", (filename, alt, last + 1))


def set_photo_alt(conn: sqlite3.Connection, photo_id: int, alt: str) -> None:
    conn.execute("UPDATE photos SET alt = ? WHERE id = ?", (alt, photo_id))


def move_photo(conn: sqlite3.Connection, photo_id: int, step: int) -> None:
    """Swap the photo with its neighbour (step -1 = earlier, +1 = later)."""
    with transaction(conn):
        photos = all_photos(conn)
        index = next((i for i, p in enumerate(photos) if p.id == photo_id), None)
        if index is None or not 0 <= index + step < len(photos):
            return
        photos[index], photos[index + step] = photos[index + step], photos[index]
        conn.executemany("UPDATE photos SET position = ? WHERE id = ?", [(i, p.id) for i, p in enumerate(photos)])


def delete_photo(conn: sqlite3.Connection, photo_id: int) -> None:
    conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))


# ----- editable texts ----------------------------------------------------------------------------


def text_overrides(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM texts")}


def set_text(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO texts (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def reset_text(conn: sqlite3.Connection, key: str) -> None:
    conn.execute("DELETE FROM texts WHERE key = ?", (key,))
