from rulebook_scraper.splitter import clean_text, html_to_text, rule_items, split_clauses

ITTF_TEXT = """
2 THE LAWS OF TABLE TENNIS
2.1 THE TABLE
2.1.1 The upper surface of the table, known as the playing surface, shall be rectangular,
2.74m long and 1.525m wide, and shall lie in a horizontal plane 76cm above the floor.
2.1.2 The playing surface shall not include the vertical sides of the tabletop.
2.6 THE SERVICE
2.6.1 Service shall start with the ball resting freely on the open palm of the server's stationary free hand.
2.6.2 The server shall then project the ball near vertically upwards, without imparting spin, so that it
rises at least 16cm after leaving the palm of the free hand and then falls without touching anything
before being struck.
12
2.6.3 As the ball is falling the server shall strike it so that it touches first his or her court and then
touches directly the receiver's court.
"""


def test_numbered_clauses_become_rules_with_section_titles():
    rules = split_clauses(ITTF_TEXT)
    ids = [r.rule_id for r in rules]
    assert ids == ["2.1.1", "2.1.2", "2.6.1", "2.6.2", "2.6.3"]
    by_id = {r.rule_id: r for r in rules}
    assert by_id["2.6.2"].title == "2.6 The Service"
    assert by_id["2.1.1"].title == "2.1 The Table"
    assert by_id["2.6.2"].text.startswith("The server shall then project the ball near vertically upwards")
    assert "rises at least 16cm" in by_id["2.6.2"].text
    assert "12" not in by_id["2.6.2"].text.split()  # the page number line is dropped


def test_toc_lines_lose_to_the_body_text():
    text = (
        "2.6.2 Service ........................ 12\n"
        "2.6.2 The server shall then project the ball near vertically upwards so that it rises at least 16cm.\n"
    )
    rules = split_clauses(text)
    assert [r.rule_id for r in rules] == ["2.6.2"]
    assert rules[0].text.startswith("The server shall")


def test_pickleball_letter_ids_and_fiba_articles():
    text = (
        "7. FAULT RULES\n"
        "7.A. Hitting the ball into the player's own side of the net or a permanent object before it goes over.\n"
        "7.B. Hitting the ball under the net or between the net and the net post.\n"
        "Art. 12 Jump ball and alternating possession\n"
        "12.1.1 A jump ball occurs when a referee tosses the ball in the centre circle between any 2 opponents.\n"
    )
    ids = [r.rule_id for r in split_clauses(text)]
    assert ids == ["7.A", "7.B", "12.1.1"]


def test_html_is_stripped_of_chrome_before_splitting():
    html = """<html><head><style>.x{}</style><script>var a=1;</script></head><body>
    <nav>Home | Rules</nav>
    <h2>2.9 A LET</h2>
    <p>2.9.1 The rally shall be a let if in service the ball touches the net assembly, if otherwise correct.</p>
    <p>2.9.2 The rally shall be a let if the service is delivered when the receiving player or pair is not ready.</p>
    <footer>© ITTF</footer></body></html>"""
    rules = split_clauses(html_to_text(html))
    assert [r.rule_id for r in rules] == ["2.9.1", "2.9.2"]
    assert rules[0].title == "2.9 A Let"
    assert "var a" not in rules[0].text and "Home" not in rules[0].text


def test_short_fragments_are_not_rules():
    assert split_clauses("3.1 Short\n3.1.1 tiny\n3.1.2 Also tiny.") == []


def test_hyphenated_line_breaks_are_joined():
    assert "service" in clean_text("ser-\nvice")


def test_rule_items_shape():
    items = rule_items(
        ITTF_TEXT,
        sport="table_tennis",
        url="https://x/laws.pdf",
        source="ITTF",
        license_note="n",
        fetched_at="2026-10-24T00:00:00+00:00",
    )
    assert set(items[0]) == {"sport", "rule_id", "title", "text", "url", "source", "license_note", "fetched_at"}
    assert items[0]["sport"] == "table_tennis" and items[0]["url"] == "https://x/laws.pdf"
