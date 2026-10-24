"""Split a rulebook's text into one record per numbered clause.

A clause starts on a line that begins with a numbered heading such as ``2.6.2`` (ITTF,
BWF, FIVB), ``12.1.1`` (FIBA) or ``7.A.`` (USA Pickleball); the clause runs until the next
heading. Short, top-level headings (``2.6 THE SERVICE``) are section titles: they are not
emitted as rules but give every clause under them its ``title``. Table-of-contents lines
(dot leaders + a page number) and lone page numbers are dropped, and when the same id
appears twice (contents + body) the longer text wins.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# "2.6.2", "12.1.1", "7.A.", "4.1.3.b" at the start of a line; the trailing dot is optional.
_HEAD = re.compile(r"^\s*(?P<id>\d{1,3}(?:\.(?:\d{1,3}|[A-Za-z]))+)\.?(?:\s+|$)(?P<rest>.*)$")
_DOT_LEADER = re.compile(r"(?:\s?\.){3,}\s*\d*\s*$|\s+\d{1,4}\s*$")
_PAGE_NUMBER = re.compile(r"^\s*(?:page\s+)?\d{1,4}\s*$", re.I)
_WS = re.compile(r"[ \t ]+")
MIN_CLAUSE_CHARS = 20
MAX_TITLE_WORDS = 8


@dataclass(frozen=True)
class Clause:
    rule_id: str
    title: str
    text: str


def _norm_id(raw: str) -> str:
    return raw.rstrip(".")


def _is_section_title(rest: str) -> bool:
    """A heading whose own text is short is a section title, not a rule."""
    words = rest.split()
    if not words or len(words) > MAX_TITLE_WORDS:
        return False
    return not rest.rstrip().endswith((".", ";", ":"))


def _title_case(s: str) -> str:
    return s.title() if s.isupper() else s


def clean_text(text: str) -> str:
    """Normalise PDF/HTML text: join hyphenated line breaks, collapse spaces, drop page numbers."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # "ser-\nvice" -> "service"
    lines = []
    for line in text.split("\n"):
        line = _WS.sub(" ", line).strip()
        if _PAGE_NUMBER.match(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def split_clauses(text: str) -> list[Clause]:
    """Clauses in document order; see the module docstring for the rules."""
    text = clean_text(text)
    out: dict[str, Clause] = {}
    order: list[str] = []
    section: dict[int, str] = {}  # depth -> title of the nearest section heading
    cur_id: str | None = None
    cur_title = ""
    buf: list[str] = []

    def flush() -> None:
        nonlocal cur_id, buf
        if cur_id is None:
            return
        body = " ".join(part for part in (p.strip() for p in buf) if part)
        body = _DOT_LEADER.sub("", body).strip() if _looks_like_toc(body) else body
        if len(body) >= MIN_CLAUSE_CHARS and (cur_id not in out or len(body) > len(out[cur_id].text)):
            if cur_id not in out:
                order.append(cur_id)
            out[cur_id] = Clause(cur_id, cur_title or _first_words(body), body)
        cur_id, buf = None, []

    for line in text.split("\n"):
        m = _HEAD.match(line)
        if not m:
            if cur_id is not None and line:
                buf.append(line)
            continue
        rid, rest = _norm_id(m.group("id")), m.group("rest").strip()
        depth = rid.count(".")
        if _is_section_title(rest) and not _looks_like_toc(rest):
            flush()
            for d in [d for d in section if d >= depth]:
                del section[d]
            section[depth] = f"{rid} {_title_case(rest)}"
            continue
        flush()
        cur_id = rid
        parent = max((d for d in section if d < depth), default=None)
        cur_title = section[parent] if parent is not None else ""
        buf = [rest]
    flush()
    return [out[i] for i in order]


def _looks_like_toc(s: str) -> bool:
    return bool(re.search(r"(?:\s?\.){3,}\s*\d*\s*$", s))


def _first_words(body: str, n: int = MAX_TITLE_WORDS) -> str:
    words = body.split()
    return " ".join(words[:n]) + ("…" if len(words) > n else "")


def html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    return soup.get_text("\n")


def pdf_to_text(data: bytes) -> str:
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def rule_items(
    text: str,
    *,
    sport: str,
    url: str,
    source: str,
    license_note: str,
    fetched_at: str,
) -> list[dict]:
    """Dataset items (interfaces-v1 §17): one per clause."""
    return [
        {
            "sport": sport,
            "rule_id": c.rule_id,
            "title": c.title,
            "text": c.text,
            "url": url,
            "source": source,
            "license_note": license_note,
            "fetched_at": fetched_at,
        }
        for c in split_clauses(text)
    ]
