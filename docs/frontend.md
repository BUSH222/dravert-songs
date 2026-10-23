# Songs on poems by P. L. Dravert (1879-1945): frontend package

> **Note:** this is the original hand-off document for the visual frontend. The templates and static files now live in
> `app/templates` and `app/static`, and the backend described in section 5 is implemented in `app/` (see the project
> README). Some details changed: templates build audio URLs with `url_for` instead of receiving them in the context,
> site texts come from `t[...]`, and descriptions/comments are trusted HTML.

A Russian-language archive of songs based on the poems of Pyotr Lyudovikovich Dravert.
This package is the **visual frontend**: server-rendered Jinja2 templates, plain Bootstrap 5.3, one small design-system stylesheet, and about 100 lines of vanilla JavaScript. There is no SPA framework and no build step. All visible site text is in Russian; everything in this document is in English.

```
dravert-songs-ui/
├── README.md                  this file
├── example_app.py             runnable FastAPI demo with fake data (shows every template's context)
├── templates/
│   ├── base.html              <html>, theme bootstrap script, header/nav, footer, script tags
│   ├── _theme_toggle.html     sun/moon button (used by base.html and login.html)
│   ├── start.html             start page "П.Л. Драверт"
│   ├── decade.html            decade page (song list + selected song)
│   ├── _song_list.html        song list, included twice (desktop sidebar + mobile offcanvas)
│   ├── _player.html           audio player card
│   ├── catalog.html           catalog, alphabetical and rating modes
│   └── login.html             admin login screen
└── static/
    ├── css/bootstrap.min.css  Bootstrap 5.3.3 (unmodified)
    ├── css/ds.css             the design system: Bootstrap variable overrides + a few .dr-* classes
    ├── js/bootstrap.bundle.min.js
    ├── js/app.js              theme toggle + audio player
    └── img/                   put the archival photos here
```

Run the demo: `pip install fastapi uvicorn jinja2`, then `uvicorn example_app:app --reload` from this folder.
(The five archive photos on the start page will show as empty grey squares until you add real images.)

---

## 1. Design system

Everything visual is defined in `static/css/ds.css`. It does three things: overrides Bootstrap's CSS variables for light and dark themes, restyles a few Bootstrap components through their own variables, and adds a handful of small `.dr-*` classes for things Bootstrap does not have (equalizer, poem, photo frame). Change the look by editing the variables at the top of that file.

### Theme

Bootstrap's native `data-bs-theme="light|dark"` on `<html>`. A tiny inline script in `base.html` sets it before first paint (saved choice from `localStorage`, otherwise the system `prefers-color-scheme`), so there is no flash of the wrong theme.

### Colour tokens

A neutral grey palette plus **one muted khaki accent**. No gradients, no shadows, only 1px borders.

| Role | Variable | Light | Dark |
|---|---|---|---|
| Page background | `--bs-body-bg` | `#FFFFFF` | `#121315` |
| Surface (header, footer, player card) | `--bs-tertiary-bg` | `#F7F8F9` | `#17191C` |
| Hover / badge background | `--bs-secondary-bg` | `#F1F3F5` | `#1D2024` |
| Border (decorative) | `--bs-border-color` | `#E3E5E8` | `#2B2F34` |
| Form field border | `--dr-input-border` | `#8A939C` | `#6B737B` |
| Text | `--bs-body-color` | `#1F2328` | `#E6E8EB` |
| Secondary text | `--bs-secondary-color` | `#5B636B` | `#A0A7AF` |
| Accent (primary button, play, equalizer, links) | `--dr-accent` | `#6A6E5C` | `#B3B79F` |
| Accent hover | `--dr-accent-hover` | `#555947` | `#C4C8B0` |
| Text on accent | `--dr-accent-on` | `#FFFFFF` | `#1A1C14` |
| Accent as text | `--dr-accent-text` | `#555947` | `#C3C7AE` |
| Accent tint (genre badge, active letter) | `--dr-accent-tint` | `#EEEFE8` | `#2A2D24` |
| Song list item background | `--dr-tint-2` | `#E4E6DB` | `#22251C` |
| Song list item hover | `--dr-tint-3` | `#D9DCCE` | `#2A2D24` |
| Error | `--bs-form-invalid-color` | `#B42318` | `#F5A5A0` |

All text/background pairs meet WCAG AA (4.5:1). The requested khaki `rgb(125,128,113)` (`#7D8071`) gives only 4.0:1 with white text, so the light-theme accent is the same hue, slightly darker (`#6A6E5C`, 5.3:1).

### Typography

Loaded from Google Fonts in `base.html` (full Cyrillic): **Inter** (400/500/600/700) for the interface and **PT Serif** for poem lyrics. Rem-based scale: page title 36px (fluid down to 26px), H2 24px, H3 20px, body 16-17px, metadata 14-15px, badges 12-14px, navigation 20px bold, poem 18-21px serif. To self-host the fonts, download the files and replace the `<link>` in `base.html` with `@font-face` rules.

### Shape and spacing

Radius 8px everywhere (4px for badges, a circle for the Play button). Spacing uses Bootstrap's scale (`p-1`...`p-5`, `gap-*`). Elevation is flat: a 1px border and a slightly different background separate layers. All buttons and rows are at least 44px tall.

---

## 2. How each page works (visually)

### Shared layout (`base.html`)
* **Header**: sticky, 57px tall, tinted background, bottom border. Left: the nav `ul.nav.nav-underline` with seven items (`П.Л. Драверт`, `1900-е` … `1940-е`, `Каталог`). The active item has bold accent text and a 2px accent underline. Right: the theme toggle. On phones the nav strip scrolls horizontally (scrollbar hidden), so all items stay one swipe away.
* **Footer**: tinted background, top border, muted small centred title.
* Child templates set `{% set active = ... %}` (`'start'`, `'1910'`, `'catalog'`) to highlight the right nav item.

### Start page (`start.html`)
Page title + subtitle ("К 150-летию со дня рождения"), then two columns. Left: five square archival photos in a vertical strip (non-interactive: no links, no hover, no lightbox). Below `lg` (992px) the strip turns into a horizontally scrollable row above the text; roughly 2.5 photos are visible, which hints that it scrolls. Right: the biography in a comfortable reading column (max 40rem, 17px/1.75).

### Decade page (`decade.html`), reused for 1900-е … 1940-е
* **Desktop (≥992px)**: two columns. Left: a 320px sidebar, sticky below the header, with its **own scroll area** (`top: 57px; height: calc(100vh - 57px)`). It contains a tinted heading and the song list. Every unselected song is slightly tinted; the **selected song is untinted with a 1px accent outline and bold accent text**. Right: the selected song as normal page content (not an iframe): title, metadata row (poem year, genre badge, read-only listen count), a two-line description, the player, the poem (serif, stanzas separated by space, optional italic epigraph, shrink-wrapped and centred as a block), and an optional "Комментарии" block that is rendered only if `song.comments` is set.
* **Phone / tablet**: the sidebar is hidden. A "Песни" button under the header opens a Bootstrap **offcanvas** with the same list (`_song_list.html` is included twice). Tapping a song is an ordinary link: the next page loads and the drawer is closed by the navigation.
* Every song has its own URL. `/decades/1910` redirects to the first song of that decade so that a song is always selected.

### Catalog (`catalog.html`)
A title and a segmented control ("По алфавиту" / "Рейтинг"), implemented as two links (`?sort=alpha`, `?sort=rating`) in a `.btn-group`, with the current one `.active`.
* **Alphabetical**: letter headings (А, Б, В …) each followed by rows: title, genre badge, decade badge, year. A sticky А-Я jump bar (desktop only) links to `#l-<letter>`; it lists only letters that have songs.
* **Rating**: numbered rows sorted by listens, each with rank, title, genre, decade, year and the listen count with a headphones icon.
* On phones every row is full width and the badges wrap under the title.

### Admin login (`login.html`)
A centred 400px card on a slightly tinted background with username, password and "Войти". When `error` is passed, the password field gets `.is-invalid` and the message appears under it. The header contains only the theme toggle. Only this screen was designed for the admin area; the panel itself is out of scope.

### Audio player (`_player.html`)
One card (1px border, subtle tinted fill): round accent Play/Pause button, a row with the decorative equalizer and `elapsed / total` time, the seek slider, and a "Загрузить" button (an `<a download>` link). Four states, set by JS through `data-state`:

| State | Play button | Equalizer | Slider |
|---|---|---|---|
| `idle` | play icon | flat | at 0, enabled |
| `loading` | spinner | flat | disabled |
| `playing` | pause icon | bouncing (`.is-playing`) | follows playback |
| `paused` | play icon | flat | enabled |

The equalizer (9 bars, CSS animation only) is decorative and not connected to real audio. It respects `prefers-reduced-motion`.

---

## 3. Bootstrap components used

| Element | Bootstrap |
|---|---|
| Header navigation | `nav.nav.nav-underline.flex-nowrap.overflow-x-auto`, `.sticky-top`, `.border-bottom` |
| Buttons | `.btn`, `.btn-primary`, `.btn-outline-secondary`, `.btn-group`, `.btn-close` |
| Song list, catalog rows | `.list-group`, `.list-group-flush`, `.list-group-item-action`, `.active` |
| Badges | `.badge`, `.bg-primary-subtle`, `.text-primary-emphasis`, `.bg-body-secondary` |
| Layout | `.row`, `.col-*`, `.g-*`, `.d-flex`, `.d-none.d-lg-block`, `.d-lg-none`, `.gap-*`, `.mx-auto` |
| Mobile song list | `.offcanvas.offcanvas-start`, `data-bs-toggle="offcanvas"` |
| Player | `.card`, `.card-body`, `.form-range`, `.spinner-border` |
| Login | `.card`, `.form-label`, `.form-control`, `.is-invalid`, `.invalid-feedback` |
| Misc | `.visually-hidden`, `.text-body-secondary`, `.object-fit-cover`, `.overflow-x-auto` |

Custom classes (`ds.css`): `.dr-header`, `.dr-songs`, `.dr-rows`, `.dr-letters`, `.dr-poem`, `.dr-epigraph`, `.dr-prose`, `.dr-player` parts (`.dr-play`, `.dr-eq`, `.dr-seek`, `.dr-dl`), `.dr-photo`, `.dr-ph`.

---

## 4. JavaScript (`static/js/app.js`)

Only two things need JavaScript; both are already implemented. Offcanvas is handled by Bootstrap's own bundle.

1. **Theme toggle**: any element with `data-theme-toggle` flips `data-bs-theme` on `<html>` and stores `light|dark` in `localStorage`. With no stored choice it follows the OS setting live. The sun/moon icon swap is pure CSS.
2. **Player**: finds every `.dr-player` and wires an `Audio` object to it.
   * `preload = 'none'`: the MP3 is not downloaded until the visitor presses Play.
   * Total duration comes from `data-duration` (seconds, from your database) until the browser knows the real one.
   * **"Player started" signal**: on the first `playing` event of a page view it sends `POST <data-start-url>` (fire-and-forget, `keepalive`). Pause/resume/seek do not resend it. **The page never changes the listen counter locally**; the number shown is whatever the server rendered.

---

## 5. Connecting the backend (FastAPI)

### Routes expected by the templates

Templates call `url_for(...)` with these route names. `example_app.py` implements them.

| Route name | Path | Purpose |
|---|---|---|
| `start` | `GET /` | start page |
| `decade` | `GET /decades/{decade}` | redirect to the first song of that decade |
| `song` | `GET /decades/{decade}/songs/{song_id}` | decade page with a selected song |
| `catalog` | `GET /catalog?sort=alpha\|rating` | catalog |
| `admin_login` | `GET/POST /admin/login` | login form and submit |
| `static` | `/static/...` | `StaticFiles` mount, name must be `static` |
| (any) | `GET /audio/{id}`, `GET /audio/{id}/download` | audio stream / attachment (URLs are passed in the context) |
| (any) | `POST /api/songs/{id}/started` | "player started" signal (URL is passed in the context) |

`templates.TemplateResponse(request, "name.html", context)`: Starlette's `Jinja2Templates` provides `url_for` to templates automatically. Behind a reverse proxy run uvicorn with `--proxy-headers` (and set `--forwarded-allow-ips`) so generated URLs use the public scheme and host.

### Context per template

| Template | Context |
|---|---|
| `start.html` | `photos`: list of `{url, alt}` (5-6 items); optional `biography_html` (trusted HTML; otherwise the built-in placeholder text is shown) |
| `decade.html` | `decade`: int (1900…1940); `songs`: list of `{id, title}` for the sidebar; `song`: see below |
| `catalog.html` | `mode`: `'alpha'` or `'rating'`; for alpha: `groups` = `[{letter, songs: [Song]}]` and `letters` = list of letters present; for rating: `ranked` = `[Song]` sorted by listens descending |
| `login.html` | `error`: str or None; `username`: str or None |

`song` (decade page): `id`, `title`, `year` (int), `genre` (str or None), `listens` (int), `description` (about two lines), `epigraph` (str or None), `stanzas` (list of lists of lines), `comments` (str or None), plus `audio_url`, `download_url`, `start_url` (strings) and `duration` (int seconds).

`Song` (catalog rows): `id`, `title`, `decade` (int, e.g. 1910, derived from `year`), `year`, `genre` (or None), `listens`.

A natural database model is one `songs` table: `id, title, description, poem_year, genre NULL, comments NULL, epigraph NULL, lyrics (text, stanzas separated by a blank line), mp3_path, listens`. The decade is `poem_year // 10 * 10`. Split lyrics into `stanzas` in Python (`[s.splitlines() for s in lyrics.strip().split("\n\n")]`).

### Audio streaming and download

* `GET /audio/{id}`: return the MP3 with `Content-Type: audio/mpeg`, `Accept-Ranges: bytes` and **HTTP Range support** (needed for seeking and for iOS Safari). `FileResponse` supports Range in current Starlette versions; otherwise implement a `StreamingResponse` with `206 Partial Content`.
* `GET /audio/{id}/download`: the same file with `Content-Disposition: attachment; filename="<slug>.mp3"`. The "Загрузить" button is a plain `<a download>` link to it.
* Do not expose raw file paths; look files up by song id.

### Listen counter

The frontend only sends `POST /api/songs/{id}/started` once per page view when playback actually begins. The server decides whether it counts. Rule from the brief: **at most once per IP and per song cookie, with the cookie expiring after 1 hour**. One straightforward implementation:

```python
from fastapi import Request, Response

COOKIE_TTL = 3600  # seconds


@app.post("/api/songs/{song_id}/started", status_code=204)
async def player_started(song_id: int, request: Request):
    cookie = f"heard_{song_id}"
    resp = Response(status_code=204)
    if request.cookies.get(cookie):  # this browser already counted within the hour
        return resp
    ip = request.client.host  # real client IP; needs --proxy-headers behind a proxy
    # Atomic "count once" for (song, ip) within the hour, e.g. Redis:
    #   if redis.set(f"heard:{song_id}:{ip}", 1, nx=True, ex=COOKIE_TTL): increment(song_id)
    # or SQL: INSERT into listens(song_id, ip_hash, created_at) with a uniqueness check on the last hour,
    # then UPDATE songs SET listens = listens + 1 WHERE id = :id
    if first_time_for_this_ip(song_id, ip):
        increment_listens(song_id)
    resp.set_cookie(cookie, "1", max_age=COOKIE_TTL, httponly=True, samesite="lax")
    return resp
```

Store a hash of the IP rather than the raw address if privacy matters. Ignore bots and prefetchers (check the `Range`/`User-Agent` on the audio route if you want to count there instead). The updated number appears on the next page load; the UI never increments it itself.

### Admin

The login template posts `username` and `password` to `admin_login`. On failure re-render the template with `error="Неверный пароль"` and status 401 (never reveal which field was wrong). On success set a signed, `httponly`, `samesite=lax` session cookie and redirect to your panel. Add a CSRF token to the form (placeholder comment in `login.html`) and rate-limit attempts.

### Photos

Put the five or six scanned photos in `static/img/` and pass them as `photos`. The frame is a square with `object-fit: cover` and a CSS `grayscale(1)` filter, so colour scans still look black-and-white. Provide meaningful `alt` text when you have captions.

---

## 6. Accessibility notes

* All controls are real `<button>`/`<a>`/`<input>` elements with labels; icon-only buttons have `aria-label`.
* The current page in the nav and the selected song carry `aria-current`.
* The player has a labelled slider; the play button label changes with state.
* Focus rings are visible (2px accent outline). Motion respects `prefers-reduced-motion`.

## 7. Known simplifications versus the design canvas

* The design canvas drew the full А-Я bar; the template shows only letters that exist in the data (every link has a target).
* The canvas showed fixed placeholder titles, text and numbers; the templates read them from the context. Biography text, photos and the poem are placeholders to be replaced.
* The canvas drew the open offcanvas as a static mock-up; in the templates Bootstrap opens it from the "Песни" button.
* Heading weight 700 is loaded; if you trim the Google Fonts request, keep 400/500/600/700 for Inter or the navigation will render lighter.
