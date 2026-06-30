#!/usr/bin/env python3
"""
Generate one blog post for jahanzaibawan.com and wire it into the site.

- Picks the next topic from automation/topics.json
- Asks Claude for a structured post (title, dek, body HTML in the site's classes)
- Writes blog/<slug>.html from a template
- Updates automation/posts.json, regenerates the cards + JSON-LD on blog.html,
  and adds the new URL to sitemap.xml
- Replenishes the topic queue when it runs low

Run from the repo root. Requires ANTHROPIC_API_KEY in the environment.
Model is configurable via BLOG_MODEL (default: claude-opus-4-8).
"""

import os
import re
import sys
import json
import html
import datetime as dt
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
import anthropic

ROOT = Path(__file__).resolve().parent.parent          # repo root (portfolio-publish)
DATA = ROOT / "automation"
BLOG_DIR = ROOT / "blog"
POSTS_JSON = DATA / "posts.json"
TOPICS_JSON = DATA / "topics.json"
BLOG_INDEX = ROOT / "blog.html"
SITEMAP = ROOT / "sitemap.xml"

MODEL = os.environ.get("BLOG_MODEL", "claude-opus-4-8")
SITE = "https://jahanzaibawan.com"
AUTHOR = "Muhammad Jahanzaib Awan"
COLORS = ["a2", "a3", "a4", "a5", "a6"]
EM_DASH = "—"

ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
        "%3Crect width='64' height='64' rx='14' fill='%2306060a'/%3E%3Ccircle cx='32' cy='32' r='28' "
        "fill='none' stroke='%2334d399' stroke-width='3'/%3E%3Ctext x='32' y='42' "
        "font-family='Arial,sans-serif' font-size='26' font-weight='800' fill='%23f6f6f8' "
        "text-anchor='middle'%3EMJ%3C/text%3E%3C/svg%3E")


class BlogPost(BaseModel):
    slug: str = Field(description="kebab-case URL slug, 3-6 words, no dates")
    title: str = Field(description="post title, 40-72 chars, no trailing period")
    dek: str = Field(description="one or two sentence standfirst shown under the title")
    excerpt: str = Field(description="punchy 1-2 sentence summary for the index card, <=180 chars")
    description: str = Field(description="meta description, <=155 chars")
    keywords: str = Field(description="6-10 comma-separated keywords")
    tag: str = Field(description="one short category label, e.g. Evaluation, Deep Learning, NLP")
    read_min: int = Field(description="estimated reading time in minutes, 4-9")
    body_html: str = Field(description=(
        "the article body as HTML. ONLY <section class=\"psec reveal\"> blocks, each with an "
        "<h2> and <p>/<ul>/<li>/<strong>/<em>. No <h1>, no <head>, no nav, no figures/images, "
        "no inline styles, no markdown. 4-7 sections. British English."))


class TopicList(BaseModel):
    topics: list[str] = Field(description="distinct, evergreen ML/data-science blog topic titles")


def strip_em(s: str) -> str:
    return s.replace(f" {EM_DASH} ", ", ").replace(EM_DASH, "-") if s else s


def fmt_date(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b')} {d.year}"


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def save(p: Path, obj: dict) -> None:
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic()


SYSTEM = (
    "You are Muhammad Jahanzaib Awan, an MSc Artificial Intelligence candidate at De Montfort "
    "University, writing a short technical post for your personal portfolio blog. Voice: precise, "
    "honest, slightly opinionated, first person. You care about rigorous evaluation, leakage-aware "
    "splits, strong baselines, and reproducibility. Teach one idea well with a concrete worked "
    "intuition. Be accurate: never invent specific statistics, citations, dataset names, or claims "
    "about your own projects. Keep it general and evergreen. CRITICAL STYLE RULE: never use an em "
    "dash (the long dash). Use commas, colons, semicolons, or full stops instead. British English."
)


def generate_post(c: anthropic.Anthropic, topic: str) -> BlogPost:
    user = [{"role": "user", "content": (
        f"Write the blog post on this topic: \"{topic}\".\n\n"
        "The body_html must use only these wrappers: "
        "<section class=\"psec reveal\"><h2>Heading</h2><p>...</p></section>, with <p>, "
        "<ul><li>, <strong>, <em> inside. No images, no code fences, no inline styles, no <h1>. "
        "Open with a section that frames why this matters, then build the idea, then close with "
        "a short practical takeaway. Do not use em dashes anywhere."
    )}]
    try:
        msg = c.messages.parse(model=MODEL, max_tokens=8000, system=SYSTEM,
                               thinking={"type": "adaptive"}, messages=user, output_format=BlogPost)
    except Exception as e:
        print(f"parse with thinking failed ({e}); retrying without thinking", file=sys.stderr)
        msg = c.messages.parse(model=MODEL, max_tokens=8000, system=SYSTEM,
                               messages=user, output_format=BlogPost)
    post = msg.parsed_output
    if post is None:
        sys.exit("model did not return a parseable post")
    # safety net: strip em dashes from every field
    for f in ("slug", "title", "dek", "excerpt", "description", "keywords", "tag", "body_html"):
        setattr(post, f, strip_em(getattr(post, f)))
    post.slug = re.sub(r"[^a-z0-9-]", "", post.slug.lower().replace(" ", "-")).strip("-")
    if not post.slug or "<section" not in post.body_html:
        sys.exit("model returned an unusable post (missing slug or body)")
    return post


def replenish(c: anthropic.Anthropic, topics: dict, want: int = 14) -> None:
    try:
        used = topics["published"] + topics["queue"]
        msg = c.messages.parse(
            model=MODEL,
            max_tokens=2000,
            system="You suggest evergreen machine-learning and data-science blog topics.",
            messages=[{"role": "user", "content": (
                f"Suggest {want} distinct, specific, evergreen ML/DS post titles suitable for a "
                "graduate ML engineer's portfolio blog (evaluation, modelling, NLP, CV, MLOps, "
                "statistics). Avoid anything overlapping these existing titles:\n- "
                + "\n- ".join(used) + "\nNo em dashes in the titles."
            )}],
            output_format=TopicList,
        )
        existing = {t.lower() for t in used}
        for t in msg.parsed_output.topics:
            t = strip_em(t).strip()
            if t and t.lower() not in existing:
                topics["queue"].append(t)
                existing.add(t.lower())
    except Exception as e:  # replenish is best-effort; never fail the run over it
        print(f"topic replenish skipped: {e}", file=sys.stderr)


def card_html(p: dict, idx: int) -> str:
    color = f"var(--{p['color']})"
    delay = " b1" if idx % 2 else ""
    if p.get("thumb"):
        thumb = (f'<div class="thumb"><img src="{esc(p["thumb"])}" '
                 f'alt="{esc(p.get("thumb_alt", p["title"]))}" loading="lazy"></div>')
    else:
        thumb = (f'<div class="thumb" style="background:linear-gradient(135deg,'
                 f'color-mix(in srgb,{color} 30%,#0b0b14),#06060a);display:grid;place-items:center;'
                 f'border-bottom:1px solid var(--line2)"><span style="font-size:11px;font-weight:700;'
                 f'letter-spacing:2px;text-transform:uppercase;color:{color}">{esc(p["tag"])}</span></div>')
    return (
        f'    <a class="pcard reveal{delay}" href="blog/{p["slug"]}.html" style="--hc:{color}">\n'
        f'      <span class="spot"></span>\n'
        f'      {thumb}\n'
        f'      <div class="pc">\n'
        f'        <div class="tag">{esc(p["tag"])} · {p["read_min"]} min read</div>\n'
        f'        <h3>{esc(p["title"])}</h3>\n'
        f'        <p>{esc(p["excerpt"])}</p>\n'
        f'        <span class="metric">{fmt_date(p["date"])}</span>\n'
        f'        <span class="more">Read →</span>\n'
        f'      </div>\n'
        f'    </a>'
    )


def render_post_page(p: dict) -> str:
    url = f"{SITE}/blog/{p['slug']}.html"
    title = esc(p["title"])
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} | {AUTHOR}</title>
<meta name="description" content="{esc(p['description'])}">
<meta name="author" content="{AUTHOR}">
<meta name="keywords" content="{esc(p['keywords'])}">
<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1">
<meta property="og:type" content="article">
<meta property="article:published_time" content="{p['date']}">
<meta property="og:site_name" content="{AUTHOR}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{esc(p['description'])}">
<meta property="og:image" content="{SITE}/assets/og.png">
<meta property="og:url" content="{url}">
<meta property="og:locale" content="en_GB">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:image" content="{SITE}/assets/og.png">
<link rel="canonical" href="{url}">
<link rel="icon" href="{ICON}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="../style.css">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "BlogPosting",
  "headline": {json.dumps(p['title'])},
  "description": {json.dumps(p['description'])},
  "url": "{url}",
  "image": "{SITE}/assets/og.png",
  "datePublished": "{p['date']}",
  "dateModified": "{p['date']}",
  "inLanguage": "en-GB",
  "author": {{ "@type": "Person", "name": "{AUTHOR}", "url": "{SITE}/" }},
  "publisher": {{ "@type": "Person", "name": "{AUTHOR}" }},
  "mainEntityOfPage": "{url}",
  "isPartOf": {{ "@type": "Blog", "@id": "{SITE}/blog.html#blog" }}
}}
</script>
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [
    {{ "@type": "ListItem", "position": 1, "name": "Home", "item": "{SITE}/" }},
    {{ "@type": "ListItem", "position": 2, "name": "Writing", "item": "{SITE}/blog.html" }},
    {{ "@type": "ListItem", "position": 3, "name": {json.dumps(p['title'])}, "item": "{url}" }}
  ]
}}
</script>
</head>
<body style="--hc:var(--{p['color']})">
<a class="skip" href="#main">Skip to content</a>
<div id="prog"></div><div class="aurora"><b></b><b></b><b></b></div><div class="grain"></div><div id="glow"></div>
<nav aria-label="Primary"><div class="bar"><a class="brand" href="../index.html"><span class="d"></span>Jahanzaib Awan</a><div class="navlinks"><a href="../index.html#work">Work</a><a href="../about.html">About</a><a href="../blog.html">Writing</a><a href="../index.html#contact">Contact</a></div></div></nav>

<div class="wrap narrow" id="main">
  <div class="phero">
    <a class="back" href="../blog.html">← All writing</a>
    <div class="tag">{esc(p['tag'])} · {p['read_min']} min read · {fmt_date(p['date'])}</div>
    <h1>{title}</h1>
    <p class="lede">{esc(p['dek'])}</p>
  </div>

{p['body_html']}

  <div class="pnav">
    <a href="../blog.html">← All writing</a>
    <a href="../index.html#work">See the project case studies →</a>
  </div>
</div>

<footer>© 2026 {AUTHOR}, AI / Machine Learning Engineer &amp; Data Scientist, Leicester, UK · <a href="https://www.linkedin.com/in/muhammad-jahanzaib-awan" rel="me noopener" target="_blank">LinkedIn</a> · <a href="https://github.com/muhammad-jahanzaib007" rel="me noopener" target="_blank">GitHub</a></footer>
<div id="toast"></div>
<script src="../app.js"></script>
</body></html>
"""


def update_blog_index(posts: list[dict]) -> None:
    text = BLOG_INDEX.read_text(encoding="utf-8")
    cards = "\n\n".join(card_html(p, i) for i, p in enumerate(posts))
    text = re.sub(r"<!--POSTS:START-->.*?<!--POSTS:END-->",
                  f"<!--POSTS:START-->\n{cards}\n<!--POSTS:END-->", text, flags=re.S)
    items = ",\n".join(
        f'    {{ "@type": "BlogPosting", "headline": {json.dumps(p["title"])}, '
        f'"url": "{SITE}/blog/{p["slug"]}.html", "datePublished": "{p["date"]}", '
        f'"author": {{ "@type": "Person", "name": "{AUTHOR}" }} }}'
        for p in posts)
    text = re.sub(r'"blogPost":\s*\[.*?\]', f'"blogPost": [\n{items}\n  ]', text, flags=re.S)
    BLOG_INDEX.write_text(text, encoding="utf-8")


def update_sitemap(posts: list[dict], today: str) -> None:
    text = SITEMAP.read_text(encoding="utf-8")
    rows = "\n".join(
        f'  <url><loc>{SITE}/blog/{p["slug"]}.html</loc><lastmod>{p["date"]}</lastmod>'
        f'<changefreq>monthly</changefreq><priority>0.7</priority></url>'
        for p in posts)
    text = re.sub(r"<!--BLOGPOSTS:START-->.*?<!--BLOGPOSTS:END-->",
                  f"<!--BLOGPOSTS:START-->\n{rows}\n  <!--BLOGPOSTS:END-->", text, flags=re.S)
    # bump blog index lastmod
    text = re.sub(r'(<loc>https://jahanzaibawan\.com/blog\.html</loc><lastmod>)[\d-]+',
                  rf'\g<1>{today}', text)
    SITEMAP.write_text(text, encoding="utf-8")


def main() -> None:
    posts_data = load(POSTS_JSON)
    topics = load(TOPICS_JSON)
    c = client()

    if not topics["queue"]:
        replenish(c, topics, want=14)
        if not topics["queue"]:
            sys.exit("no topics available and replenish failed")

    topic = topics["queue"].pop(0)
    print(f"Generating post for topic: {topic}")
    post = generate_post(c, topic)

    existing_slugs = {p["slug"] for p in posts_data["posts"]}
    today = os.environ.get("POST_DATE") or dt.datetime.now(dt.timezone.utc).date().isoformat()
    if post.slug in existing_slugs:
        post.slug = f"{post.slug}-{today.replace('-', '')}"

    entry = {
        "slug": post.slug,
        "title": post.title,
        "excerpt": post.excerpt,
        "date": today,
        "read_min": max(3, min(12, int(post.read_min))),
        "tag": post.tag,
        "color": COLORS[len(posts_data["posts"]) % len(COLORS)],
        "thumb": None,
        "thumb_alt": None,
    }

    BLOG_DIR.mkdir(exist_ok=True)
    (BLOG_DIR / f"{post.slug}.html").write_text(render_post_page({**post.model_dump(), **entry}), encoding="utf-8")

    posts_data["posts"].insert(0, entry)
    ordered = sorted(posts_data["posts"], key=lambda p: p["date"], reverse=True)
    posts_data["posts"] = ordered
    save(POSTS_JSON, posts_data)

    update_blog_index(ordered)
    update_sitemap(ordered, today)

    topics["published"].append(topic)
    if len(topics["queue"]) < 6:
        replenish(c, topics)
    save(TOPICS_JSON, topics)

    print(f"Published blog/{post.slug}.html  ({entry['title']})")


if __name__ == "__main__":
    main()
