"""Site texts the administrator can edit in place.

Every key has a default; the database only stores overrides. `kind` decides the editor and how the value is
rendered: "line" (one line of plain text), "text" (multi-line plain text) or "html" (trusted raw HTML).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from app import db

if TYPE_CHECKING:
    import sqlite3


@dataclass(frozen=True)
class TextField:
    label: str
    default: str
    kind: Literal["line", "text", "html"] = "line"
    hint: str = ""


_BIOGRAPHY = """\
<p>Пётр Людовикович Драверт (1879-1945) — учёный-геолог, исследователь Сибири и поэт. Всю жизнь он соединял строгую \
работу в экспедициях и лабораториях с тихой, внимательной лирикой, в которой природа, дорога и память о близких \
звучат почти как музыка.</p>
<p>Стихи Драверта долго оставались известны узкому кругу читателей. Они печатались в журналах и сборниках начала XX \
века, переписывались в тетради и читались вслух. Сегодня многие из них впервые звучат как песни: этот архив собирает \
мелодии, написанные на его строки, и сохраняет рядом тексты стихотворений.</p>
<p>Песни разложены по десятилетиям, от 1900-х до 1940-х годов, по году написания стихотворения. На странице каждой \
песни есть запись, которую можно послушать или загрузить, полный текст стихотворения и, если они есть, комментарии. \
Все песни собраны в каталоге: их можно просматривать по алфавиту или по числу прослушиваний.</p>
<p class="mb-0">Архив создан к 150-летию со дня рождения поэта. Фотографии и документы публикуются из семейных и \
музейных собраний, подписи и точные даты будут уточняться по мере появления новых материалов.</p>"""

TEXTS: dict[str, TextField] = {
    # Shown on every page
    "site.title": TextField("Название сайта (вкладка браузера)", "Песни на стихи Петра Людовиковича Драверта"),
    "site.short_title": TextField("Короткое название (вкладка браузера)", "Песни на стихи Драверта"),
    "nav.start": TextField("Меню: стартовая страница", "П.Л. Драверт"),
    "nav.catalog": TextField("Меню: каталог", "Каталог"),
    "footer": TextField("Подвал сайта", "Песни на стихи Петра Людовиковича Драверта (1879-1945)"),
    # Start page
    "start.heading": TextField(
        "Заголовок стартовой страницы", "Песни на стихи&nbsp;<br>Петра Людовиковича Драверта (1879-1945)", "html"
    ),
    "start.subtitle": TextField("Подзаголовок стартовой страницы", "К 150-летию со дня рождения"),
    "start.biography": TextField("Биография", _BIOGRAPHY, "html"),
    # Decade pages
    "decade.heading": TextField(
        "Заголовок списка песен", "Песни {decade}-х годов", hint="{decade} заменяется на десятилетие, например 1910"
    ),
    "decade.empty": TextField("Текст для десятилетия без песен", "Песни этого десятилетия скоро появятся.", "text"),
    "song.comments_heading": TextField("Заголовок блока комментариев", "Комментарии"),
    # Catalog
    "catalog.heading": TextField("Заголовок каталога", "Каталог"),
    "catalog.subtitle": TextField("Подзаголовок каталога", "Все песни архива"),
    "catalog.empty": TextField("Текст для пустого каталога", "В архиве пока нет песен.", "text"),
}

# Keys edited from the "Общие тексты" menu in the admin bar (they have no natural place for a pencil button).
GLOBAL_KEYS = ("site.title", "site.short_title", "nav.start", "nav.catalog", "footer")


def load_texts(conn: sqlite3.Connection) -> dict[str, str]:
    values = {key: field.default for key, field in TEXTS.items()}
    values.update({k: v for k, v in db.text_overrides(conn).items() if k in TEXTS})
    return values
