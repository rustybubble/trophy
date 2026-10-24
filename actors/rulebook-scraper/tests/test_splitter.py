"""The splitter on the synthetic laws (evals/fixtures/rulebooks/, labelled synthetic). No real rulebook text here."""

from pathlib import Path

from rulebook_scraper.splitter import (
    MAX_CLAUSE_CHARS,
    chunk_text,
    clean_text,
    html_to_text,
    pdf_to_text,
    rule_items,
    split_clauses,
)

FIXTURES = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "rulebooks"
LAWS = (FIXTURES / "synthetic_laws.txt").read_text("utf8")
SKIPS = [r"^\s*National byelaw"]
EXPECTED_IDS = [
    "2.1.1", "2.1.2", "2.1.3", "2.2.1", "2.2.2",
    "2.6.1", "2.6.2", "2.6.3", "2.6.4", "2.6.5",
    "2.9.1", "2.9.2", "2.9.3",
    "2.10.1", "2.10.2", "2.10.3", "2.10.4", "2.10.5", "2.10.6",
    "2.11.1", "2.13.1", "2.13.2", "2.14.1", "2.14.2",
]  # fmt: skip


def test_numbered_clauses_with_section_titles_and_paths():
    rules = split_clauses(LAWS, SKIPS)
    assert [r.number for r in rules] == EXPECTED_IDS
    by = {r.number: r for r in rules}
    assert by["2.6.2"].title == "2.6 The Service"
    assert by["2.6.2"].section_path == ("2 The Test Laws Of Paddle Pong", "2.6 The Service")
    assert by["2.6.2"].text.startswith("The server shall then project the ball near vertically upwards")
    assert "rises at least 20 cm" in by["2.6.2"].text  # a wrapped PDF line carried over
    assert by["2.10.4"].title == "2.10 A Point"


def test_page_numbers_toc_and_byelaw_boxes_are_dropped():
    rules = split_clauses(LAWS, SKIPS)
    text = " ".join(r.text for r in rules)
    assert "byelaw" not in text.lower()  # the national byelaw box after 2.6.5 is skipped
    assert "...." not in text  # contents lines
    by = {r.number: r for r in rules}
    assert by["2.6.2"].text.split()[-1] == "struck." and " 4 " not in by["2.6.2"].text  # page number lines
    assert by["2.6.5"].text.endswith("between the ball and the net.")


def test_byelaw_box_is_kept_without_skip_patterns():
    rules = split_clauses(LAWS)
    assert "byelaw" in {r.number: r for r in rules}["2.6.5"].text.lower()


def test_toc_lines_lose_to_the_body_text():
    text = "2.6.2 The Service ........................ 12\n"
    text += "2.6.2 The ball shall be thrown up at least twenty centimetres.\n"
    rules = split_clauses(text)
    assert [r.number for r in rules] == ["2.6.2"] and rules[0].text.startswith("The ball shall")


def test_pickleball_letter_ids_and_fiba_articles():
    text = (
        "7. FAULT RULES\n"
        "7.A. Hitting the ball into the player's own side of the net before it goes over is a fault.\n"
        "7.B. Hitting the ball under the net or between the net and the net post is a fault.\n"
        "Art. 12 Jump ball and alternating possession\n"
        "12.1.1 A jump ball occurs when a referee tosses the ball between any two opponents.\n"
    )
    assert [r.number for r in split_clauses(text)] == ["7.A", "7.B", "12.1.1"]


def test_html_is_stripped_of_chrome_before_splitting():
    html = """<html><head><style>.x{}</style><script>var a=1;</script></head><body>
    <nav>Home | Rules</nav>
    <h2>2.9 A LET</h2>
    <p>2.9.1 The rally shall be a let if in service the ball touches the net and the service is otherwise correct.</p>
    <p>2.9.2 The rally shall be a let if the service is delivered when the receiver is not ready.</p>
    <footer>(c) nobody</footer></body></html>"""
    rules = split_clauses(html_to_text(html))
    assert [r.number for r in rules] == ["2.9.1", "2.9.2"] and rules[0].title == "2.9 A Let"
    assert "var a" not in rules[0].text and "Home" not in rules[0].text


def test_short_fragments_are_not_rules():
    assert split_clauses("3.1 Short\n3.1.1 tiny\n3.1.2 Also tiny.") == []


def test_hyphenated_line_breaks_are_joined():
    assert "service" in clean_text("ser-\nvice")


def test_long_clauses_are_chunked_at_sentence_ends():
    long = {r.number: r for r in split_clauses(LAWS, SKIPS)}["2.14.1"].text
    assert len(long) > MAX_CLAUSE_CHARS
    parts = chunk_text(long)
    assert len(parts) == 2 and all(len(p) <= MAX_CLAUSE_CHARS for p in parts)
    assert parts[0].endswith(".") and " ".join(parts) == long


def test_rule_items_shape_ids_and_chunks():
    items = rule_items(LAWS, sport="paddle_pong", slug="ttl", url="https://x/laws.pdf", source="Trophy Test Laws",
                       license_note="synthetic", fetched_at="2026-10-24T00:00:00+00:00",
                       skip_patterns=SKIPS)  # fmt: skip
    assert set(items[0]) == {"sport", "rule_id", "number", "title", "text", "url", "source", "section_path",
                             "license_note", "fetched_at", "content_hash"}  # fmt: skip
    ids = [i["rule_id"] for i in items]
    assert ids[:2] == ["ttl:2.1.1", "ttl:2.1.2"] and "ttl:2.14.1" in ids and "ttl:2.14.1#2" in ids
    assert len(items) == len(EXPECTED_IDS) + 1  # 2.14.1 split in two
    assert all(len(i["text"]) <= MAX_CLAUSE_CHARS for i in items)
    assert all(len(i["content_hash"]) == 16 for i in items)
    assert items[0]["section_path"] == ["2 The Test Laws Of Paddle Pong", "2.1 The Table"]


def test_the_synthetic_pdf_splits_like_the_text():
    pdf_text = pdf_to_text((FIXTURES / "synthetic_laws.pdf").read_bytes())
    from_pdf = split_clauses(pdf_text, SKIPS)
    from_txt = split_clauses(LAWS, SKIPS)
    assert [r.number for r in from_pdf] == [r.number for r in from_txt]
    assert {r.number: r.text for r in from_pdf} == {r.number: r.text for r in from_txt}
