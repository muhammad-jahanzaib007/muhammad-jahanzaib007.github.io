#!/usr/bin/env python3
"""One-off: keep only the original project write-ups, delete the auto-generated
posts (and their card images), then rebuild blog.html and sitemap.xml.
Run from the repo root: python automation/cleanup_posts.py
"""

from generate_post import (
    update_blog_index, update_sitemap, load, save, POSTS_JSON, BLOG_DIR, ROOT,
)

KEEP = {"gru-vs-gpt2", "uav-data-leakage"}


def main():
    data = load(POSTS_JSON)
    removed = [p for p in data["posts"] if p["slug"] not in KEEP]
    data["posts"] = [p for p in data["posts"] if p["slug"] in KEEP]
    save(POSTS_JSON, data)

    for p in removed:
        slug = p["slug"]
        for path in (BLOG_DIR / f"{slug}.html", ROOT / "assets" / "blog" / f"{slug}.png"):
            if path.exists():
                path.unlink()

    update_blog_index(data["posts"])
    if data["posts"]:
        update_sitemap(data["posts"], data["posts"][0]["date"])
    print(f"kept {sorted(KEEP)}; removed {[p['slug'] for p in removed]}")


if __name__ == "__main__":
    main()
