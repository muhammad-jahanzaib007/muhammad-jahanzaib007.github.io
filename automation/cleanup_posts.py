#!/usr/bin/env python3
"""One-off: delete stub posts, requeue their topics, regenerate index + sitemap.

Removes the given slugs from posts.json, deletes their HTML page and card
image, pushes their topics back to the front of the queue so they get
rewritten at full length, then rebuilds blog.html and sitemap.xml.
Run from the repo root: python automation/cleanup_posts.py
"""

from generate_post import (
    update_blog_index, update_sitemap, load, save,
    POSTS_JSON, TOPICS_JSON, BLOG_DIR, ROOT,
)

REMOVE = ["precision-recall-vs-roc", "roc-auc-imbalanced-data"]
REQUEUE = [
    "Why ROC-AUC can mislead on imbalanced datasets",
    "Precision-recall curves versus ROC curves: when to use which",
]


def main():
    data = load(POSTS_JSON)
    data["posts"] = [p for p in data["posts"] if p["slug"] not in REMOVE]
    save(POSTS_JSON, data)

    for slug in REMOVE:
        for path in (BLOG_DIR / f"{slug}.html", ROOT / "assets" / "blog" / f"{slug}.png"):
            if path.exists():
                path.unlink()

    topics = load(TOPICS_JSON)
    existing = {t.lower() for t in topics["queue"]}
    for t in reversed(REQUEUE):
        if t.lower() not in existing:
            topics["queue"].insert(0, t)
    save(TOPICS_JSON, topics)

    update_blog_index(data["posts"])
    update_sitemap(data["posts"], data["posts"][0]["date"])
    print("cleanup done")


if __name__ == "__main__":
    main()
