#!/usr/bin/env python3
"""
Generate one blog post for jahanzaibawan.com and wire it into the site.

Uses GitHub Models (free, no API key) via the Actions GITHUB_TOKEN.
- Picks the next topic from automation/topics.json
- Asks the model for a structured post (title, dek, body HTML in the site's classes)
- Writes blog/<slug>.html from a template
- Updates automation/posts.json, regenerates the cards + JSON-LD on blog.html,
  and adds the new URL to sitemap.xml
- Replenishes the topic queue when it runs low

Run from the repo root. Requires GITHUB_TOKEN in the environment (provided
automatically inside GitHub Actions). Model is configurable via BLOG_MODEL
(default: openai/gpt-4o-mini).
"""

import os
import re
import sys
import json
import html
import datetime as dt
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent          # repo root (portfolio-publish)
DATA = ROOT / "automation"
BLOG_DIR = ROOT / "blog"
POSTS_JSON = DATA / "posts.json"
TOPICS_JSON = DATA / "topics.json"
BLOG_INDEX = ROOT / "blog.html"
SITEMAP = ROOT / "sitemap.xml"

MODEL = os.environ.get("BLOG_MODEL", "openai/gpt-4o-mini")
ENDPOINT = os.environ.get("MODELS_ENDPOINT", "https://models.github.ai/inference/chat/completions")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("MODELS_TOKEN")
# If ANTHROPIC_API_KEY is set, use Claude; otherwise fall back to free GitHub Models.
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")

SITE = "https://jahanzaibawan.com"
AUTHOR = "Muhammad Jahanzaib Awan"
COLORS = ["a2", "a3", "a4", "a5", "a6"]
EM_DASH = "—"
REQUIRED = ("slug", "title", "dek", "excerpt", "description", "keywords", "tag", "read_min", "body_html")

# JSON schema for the Claude path (structured outputs) so the API guarantees valid
# JSON regardless of quotes inside body_html.
POST_SCHEMA = {
    "type": "object",
    "properties": {k: ({"type": "integer"} if k == "read_min" else {"type": "string"}) for k in REQUIRED},
    "required": list(REQUIRED),
    "additionalProperties": False,
}
TOPICS_SCHEMA = {
    "type": "object",
    "properties": {"topics": {"type": "array", "items": {"type": "string"}}},
    "required": ["topics"],
    "additionalProperties": False,
}

ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
        "%3Crect width='64' height='64' rx='14' fill='%2306060a'/%3E%3Ccircle cx='32' cy='32' r='28' "
        "fill='none' stroke='%2334d399' stroke-width='3'/%3E%3Ctext x='32' y='42' "
        "font-family='Arial,sans-serif' font-size='26' font-weight='800' fill='%23f6f6f8' "
        "text-anchor='middle'%3EMJ%3C/text%3E%3C/svg%3E")

SYSTEM = (
    "You are Muhammad Jahanzaib Awan, an MSc Artificial Intelligence candidate at De Montfort "
    "University, writing a short technical post for your personal portfolio blog. Voice: precise, "
    "honest, slightly opinionated, first person. You care about rigorous evaluation, leakage-aware "
    "splits, strong baselines, and reproducibility. Teach one idea well with a concrete worked "
    "intuition. Be accurate: never invent specific statistics, citations, dataset names, or claims "
    "about your own projects. Keep it general and evergreen. CRITICAL STYLE RULE: never use an em "
    "dash. Use commas, colons, semicolons, or full stops instead. Use British English. "
    "Always reply with a single valid JSON object and nothing else."
)


def strip_em(s):
    return s.replace(f" {EM_DASH} ", ", ").replace(EM_DASH, "-") if isinstance(s, str) else s


def fmt_date(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b')} {d.year}"


def esc(s):
    return html.escape(str(s), quote=True)


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def save(p, obj):
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _raw_completion(user, max_tokens, schema=None):
    if ANTHROPIC_KEY:
        import anthropic
        client = anthropic.Anthropic()
        kwargs = dict(
            model=CLAUDE_MODEL, max_tokens=max_tokens, system=SYSTEM,
            thinking={"type": "disabled"},  # keep the full max_tokens for the post; no thinking spend
            messages=[{"role": "user", "content": user}],
        )
        if schema:  # structured outputs -> API guarantees valid JSON
            kwargs["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        msg = client.messages.create(**kwargs)
        return "".join(b.text for b in msg.content if b.type == "text")
    if not TOKEN:
        sys.exit("Set ANTHROPIC_API_KEY (Claude), or run in GitHub Actions (free GitHub Models).")
    resp = requests.post(
        ENDPOINT,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
                 "Accept": "application/json"},
        json={
            "model": MODEL,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            "temperature": 0.85,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        },
        timeout=120,
    )
    if resp.status_code >= 400:
        sys.exit(f"GitHub Models request failed ({resp.status_code}): {resp.text[:500]}")
    return resp.json()["choices"][0]["message"]["content"]


def chat_json(user, max_tokens=4000, schema=None):
    content = _raw_completion(user, max_tokens, schema)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.S)        # tolerate stray prose around the JSON
        if not m:
            sys.exit(f"model did not return JSON: {content[:300]}")
        return json.loads(m.group(0))


def generate_post(topic):
    base = (
        f'Write a blog post on this topic: "{topic}".\n\n'
        "Return a JSON object with these keys: slug, title, dek, excerpt, description, keywords, "
        "tag, read_min, body_html.\n"
        "- slug: kebab-case, 3-6 words, no dates\n"
        "- title: 40-72 chars, no trailing period\n"
        "- dek: one or two sentence standfirst shown under the title\n"
        "- excerpt: punchy 1-2 sentence card summary, <=180 chars\n"
        "- description: meta description, <=155 chars\n"
        "- keywords: 6-10 comma-separated keywords\n"
        "- tag: one short category label (e.g. Evaluation, Deep Learning, NLP)\n"
        "- read_min: integer 4-9 (rough; recomputed from the body)\n"
        "- body_html: the article body as HTML using ONLY "
        "<section class='psec reveal'><h2>Heading</h2><p>...</p></section> blocks, with "
        "<p>, <ul>, <li>, <strong>, <em> inside. Use single quotes for HTML attributes. "
        "The body MUST be AT LEAST 1100 words (aim 1200 to 1600) across 6 to 8 sections, each with "
        "2 to 4 substantial paragraphs. A short draft is NOT acceptable. Develop every point: give "
        "the intuition, a concrete worked example with realistic numbers, and why it matters in "
        "practice. No <h1>, no head, no nav, no images, no code fences, no inline styles, no "
        "markdown. Open by framing why the idea matters, build it up, then close with a practical "
        "takeaway. No em dashes anywhere."
    )
    words = 0
    for attempt in range(2):
        user = base if attempt == 0 else base + (
            "\n\nYour previous draft was too short. Write a FULL, in-depth article of at least "
            "1200 words across 6 to 8 well-developed sections. Do not stop early.")
        data = chat_json(user, max_tokens=10000, schema=POST_SCHEMA)
        for k in ("slug", "title", "dek", "excerpt", "description", "keywords", "tag", "body_html"):
            data[k] = strip_em(str(data.get(k, "")))
        data["slug"] = re.sub(r"[^a-z0-9-]", "", data["slug"].lower().replace(" ", "-")).strip("-")
        words = len(re.sub(r"<[^>]+>", " ", data["body_html"]).split())
        data["read_min"] = max(4, min(12, round(words / 200)))   # honest, derived from the body
        if data["slug"] and data["body_html"].count("<section") >= 3 and words >= 700:
            return data
        print(f"attempt {attempt + 1}: post too short ({words} words); "
              + ("retrying" if attempt == 0 else "giving up"))
    sys.exit(f"model returned an unusable/too-short post after retries ({words} words)")


def replenish(topics, want=14):
    try:
        used = topics["published"] + topics["queue"]
        user = (
            f"Suggest {want} distinct, specific, evergreen machine-learning / data-science blog "
            "post titles for a graduate ML engineer's portfolio (evaluation, modelling, NLP, CV, "
            "MLOps, statistics). Avoid anything overlapping these existing titles:\n- "
            + "\n- ".join(used)
            + '\nReturn a single JSON object: {"topics": ["title 1", "title 2", ...]}. No em dashes.'
        )
        data = chat_json(user, max_tokens=1200, schema=TOPICS_SCHEMA)
        existing = {t.lower() for t in used}
        for t in data.get("topics", []):
            t = strip_em(str(t)).strip()
            if t and t.lower() not in existing:
                topics["queue"].append(t)
                existing.add(t.lower())
    except SystemExit:
        raise
    except Exception as e:
        print(f"topic replenish skipped: {e}", file=sys.stderr)


def card_html(p, idx):
    color = f"var(--{p['color']})"
    delay = " b1" if idx % 2 else ""
    if p.get("thumb"):
        thumb = (f'<div class="thumb"><img src="{esc(p["thumb"])}" '
                 f'alt="{esc(p.get("thumb_alt") or p["title"])}" loading="lazy"></div>')
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


def render_post_page(p):
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
<meta property="og:image" content="{SITE}/assets/blog/{p['slug']}.png">
<meta property="og:url" content="{url}">
<meta property="og:locale" content="en_GB">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:image" content="{SITE}/assets/blog/{p['slug']}.png">
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
  "image": "{SITE}/assets/blog/{p['slug']}.png",
  "datePublished": "{p['date']}",
  "dateModified": "{p['date']}",
  "inLanguage": "en-GB",
  "author": {{ "@type": "Person", "name": "{AUTHOR}", "url": "{SITE}/", "sameAs": ["https://www.linkedin.com/in/muhammad-jahanzaib-awan", "https://github.com/muhammad-jahanzaib007"] }},
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


def update_blog_index(posts):
    text = BLOG_INDEX.read_text(encoding="utf-8")
    cards = "\n\n".join(card_html(p, i) for i, p in enumerate(posts))
    text = re.sub(r"<!--POSTS:START-->.*?<!--POSTS:END-->",
                  lambda m: f"<!--POSTS:START-->\n{cards}\n<!--POSTS:END-->", text, flags=re.S)
    items = ",\n".join(
        f'    {{ "@type": "BlogPosting", "headline": {json.dumps(p["title"])}, '
        f'"url": "{SITE}/blog/{p["slug"]}.html", "datePublished": "{p["date"]}", '
        f'"author": {{ "@type": "Person", "name": "{AUTHOR}" }} }}'
        for p in posts)
    text = re.sub(r'"blogPost":\s*\[.*?\]', lambda m: f'"blogPost": [\n{items}\n  ]', text, flags=re.S)
    BLOG_INDEX.write_text(text, encoding="utf-8")


def update_sitemap(posts, today):
    text = SITEMAP.read_text(encoding="utf-8")
    rows = "\n".join(
        f'  <url><loc>{SITE}/blog/{p["slug"]}.html</loc><lastmod>{p["date"]}</lastmod>'
        f'<changefreq>monthly</changefreq><priority>0.7</priority></url>'
        for p in posts)
    text = re.sub(r"<!--BLOGPOSTS:START-->.*?<!--BLOGPOSTS:END-->",
                  lambda m: f"<!--BLOGPOSTS:START-->\n{rows}\n  <!--BLOGPOSTS:END-->", text, flags=re.S)
    text = re.sub(r'(<loc>https://jahanzaibawan\.com/blog\.html</loc><lastmod>)[\d-]+',
                  rf'\g<1>{today}', text)
    SITEMAP.write_text(text, encoding="utf-8")


CARD_W, CARD_H = 1200, 630
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
ACCENT = (52, 211, 153)   # emerald, matches the site's #34d399 mark


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def make_card(slug, title, tag):
    """Draw a branded 1200x630 title card to assets/blog/<slug>.png (OG + thumbnail)."""
    img = Image.new("RGB", (CARD_W, CARD_H), (6, 6, 10))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, CARD_W, 8], fill=ACCENT)                       # top accent bar

    d.text((72, 92), tag.upper(), font=_font(FONT_BOLD, 26), fill=ACCENT)

    title_font = _font(FONT_BOLD, 62)
    y = 160
    for line in _wrap(d, title, title_font, CARD_W - 200)[:5]:
        d.text((72, y), line, font=title_font, fill=(246, 246, 248))
        y += 78

    d.text((72, CARD_H - 78), "Muhammad Jahanzaib Awan  |  jahanzaibawan.com",
           font=_font(FONT_REG, 30), fill=(160, 160, 170))

    cx, cy, r = CARD_W - 108, 112, 46                                # MJ monogram
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ACCENT, width=3)
    mono = _font(FONT_BOLD, 40)
    d.text((cx - d.textlength("MJ", font=mono) / 2, cy - 28), "MJ", font=mono, fill=(246, 246, 248))

    out = ROOT / "assets" / "blog"
    out.mkdir(parents=True, exist_ok=True)
    img.save(out / f"{slug}.png", "PNG")


def main():
    posts_data = load(POSTS_JSON)
    topics = load(TOPICS_JSON)

    if not topics["queue"]:
        replenish(topics, want=14)
        if not topics["queue"]:
            sys.exit("no topics available and replenish failed")

    topic = topics["queue"].pop(0)
    print(f"Generating post for topic: {topic}")
    post = generate_post(topic)

    existing_slugs = {p["slug"] for p in posts_data["posts"]}
    today = os.environ.get("POST_DATE") or dt.datetime.now(dt.timezone.utc).date().isoformat()
    if post["slug"] in existing_slugs:
        post["slug"] = f"{post['slug']}-{today.replace('-', '')}"

    entry = {
        "slug": post["slug"],
        "title": post["title"],
        "excerpt": post["excerpt"],
        "date": today,
        "read_min": post["read_min"],
        "tag": post["tag"],
        "color": COLORS[len(posts_data["posts"]) % len(COLORS)],
        "thumb": f"assets/blog/{post['slug']}.png",
        "thumb_alt": f"Cover image for the article: {post['title']}",
    }

    make_card(post["slug"], post["title"], post["tag"])
    BLOG_DIR.mkdir(exist_ok=True)
    (BLOG_DIR / f"{post['slug']}.html").write_text(render_post_page({**post, **entry}), encoding="utf-8")

    posts_data["posts"].insert(0, entry)
    posts_data["posts"] = sorted(posts_data["posts"], key=lambda p: p["date"], reverse=True)
    save(POSTS_JSON, posts_data)

    update_blog_index(posts_data["posts"])
    update_sitemap(posts_data["posts"], today)

    topics["published"].append(topic)
    if len(topics["queue"]) < 6:
        replenish(topics)
    save(TOPICS_JSON, topics)

    print(f"Published blog/{post['slug']}.html  ({entry['title']})")


if __name__ == "__main__":
    main()
