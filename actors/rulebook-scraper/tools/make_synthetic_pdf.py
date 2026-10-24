"""Write `evals/fixtures/rulebooks/synthetic_laws.pdf`, a two-page PDF of the synthetic laws, with no PDF library.

Each page is one Helvetica text object, one `Tj` per line, so `pypdf.PdfReader.extract_text()` returns the lines in
order and the splitter sees the same text as the `.txt` fixture (page numbers become their own lines, as in a real
law book). Run: `uv run python tools/make_synthetic_pdf.py` from `actors/rulebook-scraper/`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "evals" / "fixtures" / "rulebooks" / "synthetic_laws.txt"
OUT = ROOT / "evals" / "fixtures" / "rulebooks" / "synthetic_laws.pdf"
LINES_PER_PAGE = 58
FONT_PT = 9
LEADING = 11.5


def _escape(s: str) -> str:
    s = s.encode("latin-1", "replace").decode("latin-1")
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _content(lines: list[str]) -> bytes:
    body = [f"BT /F1 {FONT_PT} Tf {LEADING} TL 40 800 Td"]
    body.extend(f"({_escape(line)}) Tj T*" for line in lines)
    body.append("ET")
    return "\n".join(body).encode("latin-1")


def build_pdf(text: str, lines_per_page: int = LINES_PER_PAGE) -> bytes:
    lines = text.splitlines()
    pages = [lines[i : i + lines_per_page] for i in range(0, len(lines), lines_per_page)] or [[]]
    objects: list[bytes] = []  # 1-based object numbers in order
    font_no = 3 + 2 * len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    for i, page_lines in enumerate(pages):
        page_no, stream_no = 3 + 2 * i, 4 + 2 * i
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {stream_no} 0 R "
            f"/Resources << /Font << /F1 {font_no} 0 R >> >> >>".encode()
        )
        stream = _content(page_lines)
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        assert page_no == 3 + 2 * i and stream_no == len(objects)
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def main() -> int:
    OUT.write_bytes(build_pdf(SRC.read_text("utf8")))
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
