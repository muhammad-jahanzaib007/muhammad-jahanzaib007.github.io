"""Tests for the blog generator's pure gate functions: body_html validation
(the gate that keeps model HTML from wrecking the page), em-dash stripping,
and RSS date formatting. No network, no image rendering."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "automation"))

import generate_post as gp


def test_body_html_valid():
    body = ("<section class='psec reveal'><h2>T</h2><p>Hello <strong>world</strong>.</p>"
            "<ul><li>a</li><li>b</li></ul></section>")
    assert gp.body_html_ok(body) is True


def test_body_html_disallowed_tag_rejected():
    assert gp.body_html_ok("<section><script>alert(1)</script></section>") is False


def test_body_html_unbalanced_rejected():
    assert gp.body_html_ok("<section><p>open paragraph</section>") is False


def test_body_html_stray_close_rejected():
    assert gp.body_html_ok("<p>x</p></section>") is False


def test_body_html_void_br_ok():
    assert gp.body_html_ok("<section><p>line<br>line</p></section>") is True


def test_strip_em_dash():
    assert gp.strip_em("clear — concise") == "clear, concise"
    assert gp.strip_em("mid—word") == "mid-word"


def test_rfc822_date():
    assert gp._rfc822("2026-07-06") == "Mon, 06 Jul 2026 09:00:00 +0000"
