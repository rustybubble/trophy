"""Split a rulebook's text into one record per numbered clause (pure functions, no I/O).

A clause starts on a line that begins with a hierarchical number such as ``2.6.2`` (ITTF, BWF, FIVB),
``12.1.1`` (FIBA) or ``7.A.`` (USA Pickleball) and runs until the next numbered line, so wrapped PDF
lines carry over into the clause they belong to. A numbered line whose own text is short and does not end
a sentence (``2.6 THE SERVICE``) is a section heading: it is not emitted as a rule, but every clause under
it gets that heading chain as ``title`` / ``section_path``. Table-of-contents lines (dot leaders and a page
number), lone page numbers and paragraphs matching a source's ``skip_patterns`` (national byelaw boxes) are
dropped; when the same number appears twice (contents and body) the longer text wins. Clauses longer than
``MAX_CLAUSE_CHARS`` (Moss's chunk limit) are split into ``<number>#2``, ``#3`` … at sentence boundaries.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

# "2.6.2", "12.1.1", "7.A.", "4.1.3.b" at the start of a line; the trailing dot is optional.
_HEAD = re.compile(r"^\s*(?P<id>\d{1,3}(?:\.(?:\d{1,3}|[A-Za-z]))+)\.?(?:\s+|$)(?P<rest>.*)$")
# "2 THE LAWS OF TABLE TENNIS", "7. FAULT RULES", "Art. 12 Jump ball": a chapter heading (depth 0)
_CHAPTER = re.compile(r"^\s*(?P<art>Art(?:icle)?\.?\s+|Section\s+|Rule\s+)?(?P<id>\d{1,3})\.?\s+(?P<rest>[A-Za-z(].*)$")
_TOC = re.compile(r"(?:\s?\.){3,}\s*\d*\s*$")
_PAGE_NUMBER = re.compile(r"^\s*(?:page\s+)?\d{1,4}\s*$", re.I)
_WS = re.compile(r"[ \t ]+")
_SENTENCE_END = re.compile(r"(?<=[.;:])\s+")
# "1.50 m wide", "2.5 percent": a measurement at the start of a wrapped line, not a clause number
_UNIT_AFTER = re.compile(r"^(?:m|cm|mm|km|g|kg|s|sec|in|ft|%|percent|per|points?|met(?:re|er)s?|seconds?)\b", re.I)
MIN_CLAUSE_CHARS = 20
MAX_CLAUSE_CHARS = 2000
MAX_TITLE_WORDS = 8


@dataclass(frozen=True)
class Clause:
    number: str
    title: str
    text: str
    section_path: tuple[str, ...] = field(default=())


def _is_section_title(rest: str) -> bool:
    """A numbered line whose own text is short and does not end a sentence is a section heading."""
    words = rest.split()
    if not words or len(words) > MAX_TITLE_WORDS:
        return False
    return not rest.rstrip().endswith((".", ";", ":"))


def _chapter_heading(line: str) -> tuple[int, str] | None:
    """(chapter number, heading) when the line is a short chapter title: all caps, or prefixed Art./Section/Rule."""
    m = _CHAPTER.match(line)
    if not m:
        return None
    rest = m.group("rest").strip()
    words = rest.split()
    if not words or len(words) > MAX_TITLE_WORDS or rest.endswith((".", ";", ":", ",")) or _TOC.search(rest):
        return None
    letters = [c for c in rest if c.isalpha()]
    caps = letters and sum(c.isupper() for c in letters) / len(letters) >= 0.8
    if not (caps or m.group("art")):
        return None
    return int(m.group("id")), f"{m.group('id')} {_title_case(rest)}"


def _title_case(s: str) -> str:
    return s.title() if s.isupper() else s


def _first_words(body: str, n: int = MAX_TITLE_WORDS) -> str:
    words = body.split()
    return " ".join(words[:n]) + ("…" if len(words) > n else "")


def clean_text(text: str) -> str:
    """Normalise PDF/HTML text: join hyphenated line breaks, collapse spaces, drop page-number lines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # "ser-\nvice" -> "service"
    lines = []
    for line in text.split("\n"):
        line = _WS.sub(" ", line).strip()
        if _PAGE_NUMBER.match(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def compile_skips(patterns: list[str] | None) -> list[re.Pattern[str]]:
    return [re.compile(p, re.I) for p in (patterns or [])]


def split_clauses(text: str, skip_patterns: list[str] | None = None) -> list[Clause]:
    """Clauses in document order; see the module docstring for the rules."""
    skips = compile_skips(skip_patterns)
    text = clean_text(text)
    out: dict[str, Clause] = {}
    order: list[str] = []
    section: dict[int, str] = {}  # depth -> heading of the nearest section at that depth
    cur: str | None = None
    cur_path: tuple[str, ...] = ()
    buf: list[str] = []
    skipping = False  # inside a paragraph matched by skip_patterns, until the next numbered line

    def flush() -> None:
        nonlocal cur, buf
        if cur is None:
            return
        body = " ".join(p for p in (p.strip() for p in buf) if p)
        if len(body) >= MIN_CLAUSE_CHARS and (cur not in out or len(body) > len(out[cur].text)):
            if cur not in out:
                order.append(cur)
            out[cur] = Clause(cur, cur_path[-1] if cur_path else _first_words(body), body, cur_path)
        cur, buf = None, []

    chapter: int | None = None

    for line in text.split("\n"):
        m = _HEAD.match(line)
        if not m:
            ch = _chapter_heading(line)
            if ch is not None:
                flush()
                skipping = False
                chapter, heading = ch
                section.clear()
                section[0] = heading
                continue
            if any(s.search(line) for s in skips):
                skipping = True
            if cur is not None and line and not skipping:
                buf.append(line)
            continue
        number, rest = m.group("id").rstrip("."), m.group("rest").strip()
        if _UNIT_AFTER.match(rest) or not _plausible_next(number, cur, chapter):
            if cur is not None and not skipping:
                buf.append(line)
            continue
        skipping = False
        if any(s.search(line) for s in skips):
            flush()
            skipping = True
            continue
        if _TOC.search(rest):  # a contents line: never a clause; the body occurrence follows later
            flush()
            continue
        depth = number.count(".")
        if _is_section_title(rest):
            flush()
            for d in [d for d in section if d >= depth]:
                del section[d]
            section[depth] = f"{number} {_title_case(rest)}"
            continue
        flush()
        cur = number
        cur_path = tuple(section[d] for d in sorted(section) if d < depth)
        buf = [rest]
    flush()
    return [out[n] for n in order]


def _plausible_next(number: str, cur: str | None, chapter: int | None) -> bool:
    """Inside clause 2.x a line starting "1.50" is a wrapped measurement, not a clause: chapters go in order."""
    base = chapter if chapter is not None else (int(cur.split(".")[0]) if cur else None)
    if base is None:
        return True
    return int(number.split(".")[0]) in (base, base + 1)


def chunk_text(text: str, limit: int = MAX_CLAUSE_CHARS) -> list[str]:
    """Split at sentence ends so every piece is <= limit chars (a single over-long sentence is cut hard)."""
    if len(text) <= limit:
        return [text]
    pieces, cur = [], ""
    for sent in _SENTENCE_END.split(text):
        while len(sent) > limit:
            pieces.append(sent[:limit].rstrip())
            sent = sent[limit:].lstrip()
        if cur and len(cur) + 1 + len(sent) > limit:
            pieces.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        pieces.append(cur)
    return pieces


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
    slug: str,
    url: str,
    source: str,
    license_note: str,
    fetched_at: str,
    skip_patterns: list[str] | None = None,
) -> list[dict]:
    """Dataset items, one per clause (or clause chunk): the RuleDoc shape in the actor README."""
    items = []
    for c in split_clauses(text, skip_patterns):
        parts = chunk_text(c.text)
        for i, part in enumerate(parts, start=1):
            number = c.number if i == 1 else f"{c.number}#{i}"
            items.append(
                {
                    "sport": sport,
                    "rule_id": f"{slug}:{number}",
                    "number": number,
                    "title": c.title,
                    "text": part,
                    "url": url,
                    "source": source,
                    "section_path": list(c.section_path),
                    "license_note": license_note,
                    "fetched_at": fetched_at,
                    "content_hash": hashlib.sha256(part.encode("utf8")).hexdigest()[:16],
                }
            )
    return items
