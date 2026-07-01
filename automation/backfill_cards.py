#!/usr/bin/env python3
"""One-off: give the older posts a branded title card (image + og:image).

Generates assets/blog/<slug>.png for the pre-image-feature posts, repoints
their og:image / twitter:image / BlogPosting image at the card, and uses the
card as the index thumbnail only where a post has none (keeps real result
figures where they already exist). Reuses make_card / update_* from
generate_post. Run from the repo root: python automation/backfill_cards.py
"""

from generate_post import (
    make_card, update_blog_index, update_sitemap, load, save,
    POSTS_JSON, BLOG_DIR, SITE,
)

SLUGS = ["roc-auc-imbalanced-data", "gru-vs-gpt2", "uav-data-leakage"]
OLD_IMG = f"{SITE}/assets/og.png"


def main():
    data = load(POSTS_JSON)
    by_slug = {p["slug"]: p for p in data["posts"]}

    for slug in SLUGS:
        p = by_slug[slug]
        make_card(slug, p["title"], p["tag"])
        card_url = f"{SITE}/assets/blog/{slug}.png"

        page = BLOG_DIR / f"{slug}.html"
        page.write_text(page.read_text(encoding="utf-8").replace(OLD_IMG, card_url),
                        encoding="utf-8")

        if not p.get("thumb"):                     # roc-auc: no figure, use the card
            p["thumb"] = f"assets/blog/{slug}.png"
            p["thumb_alt"] = f"Cover image for the article: {p['title']}"

    save(POSTS_JSON, data)
    update_blog_index(data["posts"])
    update_sitemap(data["posts"], data["posts"][0]["date"])
    print("backfill done")


if __name__ == "__main__":
    main()
