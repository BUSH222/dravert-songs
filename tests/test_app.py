import re
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from mutagen.id3 import APIC, COMM, ID3, TALB, TIT2, TPE1, TPE2

from app.config import Settings
from app.main import create_app
from app.security import LoginThrottle, safe_next

if TYPE_CHECKING:
    from collections.abc import Iterator

PASSWORD = "test-password"
LYRICS = "Первая строка,\nвторая строка.\n\nТретья строка,\nчетвёртая."


def fake_mp3(frames: int = 200) -> bytes:
    """Silent MPEG-1 Layer III frames (128 kbit/s, 44.1 kHz): 417 bytes each, about 5 seconds for 200."""
    header = bytes([0xFF, 0xFB, 0x90, 0x00])
    return (header + bytes(417 - len(header))) * frames


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(admin_username="admin", admin_password=PASSWORD, secret_key="s" * 32, data_dir=tmp_path)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    app.state.login_throttle = LoginThrottle(min_interval=0)  # tests log in many times in a row
    with TestClient(app) as c:
        yield c


def csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "no CSRF token on the page"
    return str(match.group(1))


def login(client: TestClient, password: str = PASSWORD, next_url: str = ""):
    token = csrf(client.get("/admin/login").text)
    data = {"username": "admin", "password": password, "csrf_token": token, "next": next_url}
    return client.post("/admin/login", data=data, follow_redirects=False)


def admin_token(client: TestClient) -> str:
    return csrf(client.get("/admin/songs").text)


def create_song(client: TestClient, **fields) -> int:
    data = {"title": "Вечерняя тропа", "year": "1912", "genre": "Романс", "lyrics": LYRICS, "csrf_token": ""}
    data |= {k: str(v) for k, v in fields.items()}
    data["csrf_token"] = admin_token(client)
    files = {"audio": ("song.mp3", fake_mp3(), "audio/mpeg")}
    response = client.post("/admin/songs/new", data=data, files=files, follow_redirects=False)
    assert response.status_code == 303, response.text
    match = re.search(r"/admin/songs/(\d+)", response.headers["location"])
    assert match
    return int(match.group(1))


# ----- public pages ------------------------------------------------------------------------------


def test_public_pages_with_empty_database(client: TestClient) -> None:
    assert "Драверт" in client.get("/").text
    assert "Песни этого десятилетия скоро появятся." in client.get("/decades/1910").text
    assert "В архиве пока нет песен." in client.get("/catalog").text
    assert client.get("/catalog?sort=rating").status_code == 200
    missing = client.get("/decades/1950")
    assert missing.status_code == 404
    assert "Страница не найдена" in missing.text


def test_no_admin_controls_for_visitors(client: TestClient) -> None:
    html = client.get("/").text
    assert "data-edit-text" not in html
    assert "admin.js" not in html


# ----- login -------------------------------------------------------------------------------------


def test_admin_pages_redirect_to_login(client: TestClient) -> None:
    response = client.get("/admin/songs", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/admin/login?next=%2Fadmin%2Fsongs")


def test_login_and_logout(client: TestClient) -> None:
    assert login(client, "wrong").status_code == 401
    response = login(client, next_url="/admin/photos")
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/photos"
    assert client.get("/admin/songs").status_code == 200
    assert "data-edit-text" in client.get("/").text
    for page in ("/decades/1900", "/catalog", "/admin/photos", "/admin/songs/new?year=1920"):
        assert client.get(page).status_code == 200, page

    client.post("/admin/logout", data={"csrf_token": admin_token(client)})
    assert client.get("/admin/songs", follow_redirects=False).status_code == 303


def test_login_requires_csrf_token(client: TestClient) -> None:
    client.get("/admin/login")
    data = {"username": "admin", "password": PASSWORD, "csrf_token": "forged"}
    assert client.post("/admin/login", data=data).status_code == 400


def test_login_is_throttled(client: TestClient) -> None:
    for _ in range(5):
        assert login(client, "wrong").status_code == 401
    blocked = login(client)  # even the right password waits now
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_throttle_rules() -> None:
    now = [0.0]
    throttle = LoginThrottle(min_interval=1, max_failures=3, global_max_failures=5, window=60, clock=lambda: now[0])
    assert throttle.check("a") == 0
    assert throttle.check("a") == 1  # too fast
    now[0] += 1
    assert throttle.check("a") == 0
    for _ in range(3):
        throttle.failure("a")
    now[0] += 2
    assert throttle.check("a") > 0  # too many failures
    assert throttle.check("b") == 0  # other addresses are not affected
    for _ in range(2):
        throttle.failure("c")
    now[0] += 2
    assert throttle.check("d") > 0  # global limit reached
    now[0] += 60
    assert throttle.check("a") == 0  # window passed


def test_safe_next() -> None:
    assert safe_next("/admin/photos", "/x") == "/admin/photos"
    for bad in ("//evil.example", "https://evil.example", "/\\evil.example", "", None):
        assert safe_next(bad, "/x") == "/x"


# ----- songs -------------------------------------------------------------------------------------


def test_admin_post_requires_csrf(client: TestClient) -> None:
    login(client)
    response = client.post("/admin/songs/new", data={"title": "X", "year": "1910", "csrf_token": "bad"})
    assert response.status_code == 403


def test_create_song_and_view_it(client: TestClient) -> None:
    login(client)
    song_id = create_song(client, description="<b>Описание</b>", comments="<i>Комментарий</i>")

    redirect = client.get("/decades/1910", follow_redirects=False)
    assert redirect.headers["location"].endswith(f"/decades/1910/songs/{song_id}")
    html = client.get(f"/decades/1910/songs/{song_id}").text
    assert "Вечерняя тропа" in html
    assert "Первая строка,<br>вторая строка." in html
    assert "<b>Описание</b>" in html  # trusted HTML is not escaped
    assert "<i>Комментарий</i>" in html
    assert 'data-duration="5"' in html
    assert "Романс" in client.get("/catalog").text

    # a wrong decade in the URL redirects to the right one
    moved = client.get(f"/decades/1920/songs/{song_id}", follow_redirects=False)
    assert moved.headers["location"].endswith(f"/decades/1910/songs/{song_id}")


def test_audio_streaming_and_download(client: TestClient) -> None:
    login(client)
    song_id = create_song(client)
    full = client.get(f"/audio/{song_id}")
    assert full.status_code == 200
    assert full.headers["content-type"] == "audio/mpeg"
    assert full.headers["accept-ranges"] == "bytes"
    partial = client.get(f"/audio/{song_id}", headers={"Range": "bytes=0-99"})
    assert partial.status_code == 206
    assert len(partial.content) == 100
    download = client.get(f"/audio/{song_id}/download")
    assert download.headers["content-disposition"].startswith("attachment")
    assert client.get("/audio/999").status_code == 404


def test_invalid_song_form_is_shown_again(client: TestClient) -> None:
    login(client)
    data = {"title": "Песня", "year": "1899", "csrf_token": admin_token(client)}
    response = client.post("/admin/songs/new", data=data)
    assert response.status_code == 400
    assert "Год стихотворения должен быть от 1900 до 1949." in response.text

    data |= {"year": "1901"}
    files = {"audio": ("bad.mp3", b"not an mp3 at all", "audio/mpeg")}
    response = client.post("/admin/songs/new", data=data, files=files)
    assert response.status_code == 400
    assert "MP3" in response.text


def test_edit_and_delete_song(client: TestClient, settings: Settings) -> None:
    login(client)
    song_id = create_song(client)
    old_files = set(settings.audio_dir.iterdir())
    data = {"title": "Новое название", "year": "1934", "lyrics": LYRICS, "listens": "42"}
    data["csrf_token"] = admin_token(client)
    files = {"audio": ("new.mp3", fake_mp3(400), "audio/mpeg")}
    response = client.post(f"/admin/songs/{song_id}", data=data, files=files, follow_redirects=False)
    assert response.status_code == 303
    html = client.get(f"/decades/1930/songs/{song_id}").text
    assert "Новое название" in html
    assert "Прослушано: 42" in html
    assert not old_files & set(settings.audio_dir.iterdir())  # the replaced file is removed

    # saving without choosing a new file keeps the recording
    data["csrf_token"] = admin_token(client)
    client.post(f"/admin/songs/{song_id}", data=data, files={"audio": ("", b"", "application/octet-stream")})
    assert client.get(f"/audio/{song_id}").status_code == 200

    client.post(f"/admin/songs/{song_id}/delete", data={"csrf_token": admin_token(client)})
    assert client.get(f"/decades/1930/songs/{song_id}").status_code == 404
    assert not list(settings.audio_dir.iterdir())


def test_listen_counter(client: TestClient) -> None:
    login(client)
    song_id = create_song(client)
    url = f"/api/songs/{song_id}/started"
    assert client.post(url).status_code == 204
    assert client.post(url).status_code == 204  # same browser (cookie)
    client.cookies.delete(f"heard_{song_id}")
    assert client.post(url).status_code == 204  # same IP, new browser
    assert "Прослушано: 1" in client.get(f"/decades/1910/songs/{song_id}").text
    assert client.post("/api/songs/999/started").status_code == 404


# ----- texts and photos --------------------------------------------------------------------------


def test_edit_site_text(client: TestClient) -> None:
    login(client)
    data = {"key": "start.subtitle", "value": "Новый\nподзаголовок", "next": "/", "csrf_token": admin_token(client)}
    response = client.post("/admin/texts", data=data, follow_redirects=False)
    assert response.headers["location"] == "/"
    assert "Новый подзаголовок" in client.get("/").text

    data |= {"restore_default": "1", "csrf_token": admin_token(client)}
    client.post("/admin/texts", data=data)
    assert "К 150-летию со дня рождения" in client.get("/").text

    data |= {"key": "no.such.key", "csrf_token": admin_token(client)}
    assert client.post("/admin/texts", data=data).status_code == 400


def test_photos(client: TestClient, settings: Settings) -> None:
    login(client)
    files = [("files", ("a.jpg", b"jpeg-a", "image/jpeg")), ("files", ("b.png", b"png-b", "image/png"))]
    client.post("/admin/photos", data={"alt": "Драверт", "csrf_token": admin_token(client)}, files=files)
    html = client.get("/").text
    urls = re.findall(r'src="[^"]*/media/photos/([0-9a-f]+\.(?:jpg|png))"', html)
    assert [Path(u).suffix for u in urls] == [".jpg", ".png"]
    assert client.get(f"/media/photos/{urls[0]}").content == b"jpeg-a"

    ids = re.findall(r"/admin/photos/(\d+)/move", client.get("/admin/photos").text)[::2]
    client.post(f"/admin/photos/{ids[1]}/move", data={"direction": "up", "csrf_token": admin_token(client)})
    reordered = re.findall(r"/media/photos/([0-9a-f]+\.(?:jpg|png))", client.get("/").text)
    assert reordered == [urls[1], urls[0]]

    client.post(f"/admin/photos/{ids[0]}/delete", data={"csrf_token": admin_token(client)})
    assert len(list(settings.photos_dir.iterdir())) == 1

    bad = [("files", ("notes.txt", b"x", "text/plain"))]
    response = client.post("/admin/photos", data={"csrf_token": admin_token(client)}, files=bad)
    assert response.status_code == 400


def test_uploaded_mp3_tags_are_cleaned(client: TestClient, settings: Settings) -> None:
    login(client)
    dirty = ID3()
    dirty.add(TIT2(encoding=3, text="Old"))
    dirty.add(TPE1(encoding=3, text=["A", "B"]))
    dirty.add(TPE2(encoding=3, text="Album artist"))
    dirty.add(COMM(encoding=3, lang="eng", desc="", text="a comment"))
    dirty.add(APIC(encoding=3, mime="image/png", type=3, desc="", data=b"png"))
    dirty.add(TALB(encoding=3, text="Album"))
    buf = BytesIO()
    dirty.save(buf)
    data = {"title": "Вечерняя тропа", "year": "1912", "lyrics": LYRICS, "csrf_token": admin_token(client)}
    files = {"audio": ("song.mp3", buf.getvalue() + fake_mp3(), "audio/mpeg")}
    response = client.post("/admin/songs/new", data=data, files=files, follow_redirects=False)
    assert response.status_code == 303

    def tags() -> ID3:
        return ID3(next(settings.audio_dir.iterdir()))

    t = tags()
    assert t["TIT2"].text == ["Вечерняя тропа"]
    assert t["TPE1"].text == ["P.L. Dravert"]
    assert str(t["TDRC"].text[0]) == "1912"
    assert not {"TPE2", "COMM::eng", "APIC:"} & set(t)
    assert t["TALB"].text == ["Album"]  # unrelated frames are left alone

    song_id = int(response.headers["location"].split("/admin/songs/")[1].split("?")[0])
    data |= {"title": "Новое", "year": "1920", "csrf_token": admin_token(client)}
    client.post(f"/admin/songs/{song_id}", data=data, files={"audio": ("", b"", "application/octet-stream")})
    t = tags()
    assert t["TIT2"].text == ["Новое"]
    assert str(t["TDRC"].text[0]) == "1920"
