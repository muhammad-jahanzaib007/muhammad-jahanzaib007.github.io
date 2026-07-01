#!/usr/bin/env python3
"""Share the newest blog post to the LinkedIn member feed (Posts API).

Runs after a post is published. No-ops if LINKEDIN_ACCESS_TOKEN is unset, so it
is safe to wire in before the secret exists.

Env:
  LINKEDIN_ACCESS_TOKEN  member access token with the w_member_social scope
                         (required; without it this script just skips).
  LINKEDIN_AUTHOR_URN    e.g. "urn:li:person:abc123" (optional; if unset it is
                         derived from /v2/userinfo, which needs the openid+profile
                         scopes on the token).
  LINKEDIN_VERSION       LinkedIn-Version header, default "202505". Bump the
                         yyyymm if LinkedIn deprecates it (repo var, no code change).

The post text embeds the article URL; LinkedIn unfurls it into a rich card using
the post's og:title / og:image (the branded card make_card generated).
"""

import os
import re
import sys
import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
POSTS_JSON = ROOT / "automation" / "posts.json"
SITE = "https://jahanzaibawan.com"

TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
AUTHOR = os.environ.get("LINKEDIN_AUTHOR_URN")
VERSION = os.environ.get("LINKEDIN_VERSION", "202606")


def _hashtag(tag):
    return "#" + re.sub(r"[^A-Za-z0-9]", "", tag)


def author_urn(headers):
    if AUTHOR:
        return AUTHOR
    r = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers, timeout=30)
    if r.status_code == 200 and r.json().get("sub"):
        return f"urn:li:person:{r.json()['sub']}"
    sys.exit(f"Could not resolve author URN (set LINKEDIN_AUTHOR_URN). "
             f"userinfo {r.status_code}: {r.text[:200]}")


def upload_image(headers, owner, post):
    """Upload the post's card image, return its urn:li:image URN (or None on failure)."""
    thumb = post.get("thumb")
    if not thumb:
        return None
    path = ROOT / thumb
    if not path.exists():
        print(f"card image not found ({path}); posting without image.")
        return None
    init = requests.post(
        "https://api.linkedin.com/rest/images?action=initializeUpload",
        headers=headers,
        data=json.dumps({"initializeUploadRequest": {"owner": owner}}),
        timeout=30,
    )
    if init.status_code not in (200, 201):
        print(f"image init failed ({init.status_code}): {init.text[:200]}; posting without image.")
        return None
    value = init.json()["value"]
    up = requests.put(value["uploadUrl"], data=path.read_bytes(),
                      headers={"Authorization": f"Bearer {TOKEN}"}, timeout=60)
    if up.status_code not in (200, 201):
        print(f"image upload failed ({up.status_code}); posting without image.")
        return None
    return value["image"]


def main():
    if not TOKEN:
        print("LINKEDIN_ACCESS_TOKEN not set; skipping LinkedIn share.")
        return

    post = json.loads(POSTS_JSON.read_text(encoding="utf-8"))["posts"][0]
    url = f"{SITE}/blog/{post['slug']}.html"
    tags = " ".join(_hashtag(t) for t in ("MachineLearning", "DataScience", post["tag"]))
    commentary = (
        f"New post: {post['title']}\n\n"
        f"{post['excerpt']}\n\n"
        f"Read it here: {url}\n\n{tags}"
    )

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": VERSION,
    }
    urn = author_urn(headers)
    body = {
        "author": urn,
        "commentary": commentary,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReblogDisabledByAuthor": False,
    }

    image_urn = upload_image(headers, urn, post)
    if image_urn:                                   # native image post with the branded card
        body["content"] = {"media": {"id": image_urn, "title": post["title"][:180]}}

    r = requests.post("https://api.linkedin.com/rest/posts", headers=headers,
                      data=json.dumps(body), timeout=30)
    if r.status_code in (200, 201):
        print(f"Shared to LinkedIn (id: {r.headers.get('x-restli-id', 'n/a')})")
    elif r.status_code == 401:
        sys.exit("LinkedIn 401: token invalid or expired (member tokens last ~60 days). "
                 "Re-authorize and update the LINKEDIN_ACCESS_TOKEN secret.")
    else:
        sys.exit(f"LinkedIn post failed ({r.status_code}): {r.text[:400]}")


if __name__ == "__main__":
    main()
