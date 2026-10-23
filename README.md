# Песни на стихи П.Л. Драверта

Archive of songs on poems by Pyotr Lyudovikovich Dravert (1879-1945). FastAPI + Jinja2 + SQLite, server-rendered
Bootstrap pages, no build step. All site text is in Russian.

## Run

```sh
cp .env.example .env        # then set ADMIN_PASSWORD and SECRET_KEY (already done on the dev machine)
uv sync
uv run main.py --reload     # http://127.0.0.1:8000, admin at /admin/login
```

`main.py` options: `--host`, `--port`, `--reload`, `--proxy` (trust `X-Forwarded-*` from a reverse proxy on
127.0.0.1, so client IPs and URLs are correct). Over HTTPS also set `SECURE_COOKIES=true` in `.env`.

Checks: `uv run ruff check .`, `uv run ruff format --check .`, `uv run ty check .`, `uv run pytest`.

## Layout

```
main.py              starts uvicorn (app.main:create_app)
app/
  config.py          settings from .env
  db.py              SQLite schema and queries (stdlib sqlite3, no ORM)
  texts.py           registry of editable site texts with their defaults
  security.py        admin session, CSRF tokens, login throttling
  web.py             templates, DB dependency, context shared by all templates
  routes/public.py   start page, decades, catalog, audio, listen counter
  routes/admin.py    login, songs, photos, texts
  templates/         Jinja2 (admin/ holds the admin-only pages)
  static/            Bootstrap, ds.css design system, app.js (player), admin.js
data/                created on first run, git-ignored
  maindb.db          the database
  audio/, photos/    uploaded files (random names; looked up by id)
docs/frontend.md     original design hand-off for the templates
tests/
```

## Administrator

There is a single account and no registration: `ADMIN_USERNAME` / `ADMIN_PASSWORD` in `.env`. Changing the password
logs out existing sessions.

When logged in, an admin bar appears under the header and the public pages show dashed pencil buttons:

* **Texts**: every heading, subtitle, the biography, empty-state messages, the footer, menu labels and browser titles
  are editable in place (the "Общие тексты" menu covers the ones without a natural spot). Values are stored as
  overrides in the `texts` table; "Вернуть исходный текст" restores the default from `app/texts.py`. Biography and
  start heading are raw HTML.
* **Songs** (`/admin/songs`): add, edit, delete. Fields: title, poem year (decides the decade, 1900-1949), genre
  (free text with autocomplete), description and comments (raw HTML), epigraph, lyrics (stanzas separated by a blank
  line), listen count, MP3 file (duration is read automatically). Songs are ordered by poem year, then title.
* **Photos** (`/admin/photos`): upload several at once, edit captions, reorder, delete.

The decades (1900-е … 1940-е) are fixed.

## Security notes

* Session: signed cookie (`SECRET_KEY`), `HttpOnly`, `SameSite=Lax`, 7 days.
* Every admin form carries a CSRF token, including the login form.
* Login throttling (in memory, per process): one attempt per second per IP, at most 5 wrong passwords per IP per
  5 minutes, and 100 wrong passwords in total per 5 minutes. Run a single uvicorn worker, or the limits apply per
  worker.
* Listen counter: at most once per hour per browser (cookie) and per IP (stored as a keyed hash, not the raw address).
