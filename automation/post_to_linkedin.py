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
import time
import datetime as dt
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
POSTS_JSON = ROOT / "automation" / "posts.json"
RECEIPT = ROOT / ".github" / "last-share.txt"
SITE = "https://jahanzaibawan.com"

# Catch-up window: share any post from the last N days that has no li_shared
# flag yet (a failed share is retried on the next run instead of being lost).
SHARE_WINDOW_DAYS = 3
MAX_SHARES_PER_RUN = 2

# IndexNow (Bing & friends; Google retired its ping endpoint). The key file
# <key>.txt lives at the site root, as the protocol requires.
INDEXNOW_KEY = "d20abba1e462424ca821cbf6d36021f0"

TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
AUTHOR = os.environ.get("LINKEDIN_AUTHOR_URN")
VERSION = os.environ.get("LINKEDIN_VERSION", "202606")


def _hashtag(tag):
    return "#" + re.sub(r"[^A-Za-z0-9]", "", tag)


def request_pages_rebuild():
    """Ask GitHub to rebuild the Pages site (recovers from a failed deploy).

    Needs GITHUB_TOKEN with the pages:write permission; silently skips without it.
    """
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        print("GITHUB_TOKEN/GITHUB_REPOSITORY not set; cannot request a Pages rebuild.")
        return
    r = requests.post(
        f"https://api.github.com/repos/{repo}/pages/builds",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json"},
        timeout=30,
    )
    print(f"requested Pages rebuild: {r.status_code} {r.text[:200]}")


def wait_until_live(url, timeout=900, interval=20, rebuild_after=300):
    """Poll the article URL until GitHub Pages serves it.

    The share step runs seconds after the git push, but the Pages build takes
    minutes (and the build itself sometimes fails outright — 2026-07-04 a failed
    build left a LinkedIn post pointing at a 404 for hours). Polls the exact URL
    readers will click; if it is still missing after `rebuild_after` seconds,
    requests one Pages rebuild and keeps waiting.
    """
    start = time.time()
    rebuild_requested = False
    while time.time() - start < timeout:
        try:
            r = requests.head(url, timeout=15, allow_redirects=True)
            if r.status_code == 200:
                return True
            print(f"not live yet ({r.status_code}): {url}")
        except requests.RequestException as e:
            print(f"not live yet ({e.__class__.__name__}): {url}")
        if not rebuild_requested and time.time() - start > rebuild_after:
            request_pages_rebuild()
            rebuild_requested = True
        time.sleep(interval)
    return False


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


def ping_indexnow(urls):
    """Tell Bing/IndexNow about new URLs. Best-effort; never fails the run."""
    if not urls:
        return
    try:
        r = requests.post("https://api.indexnow.org/indexnow",
                          json={"host": "jahanzaibawan.com", "key": INDEXNOW_KEY,
                                "keyLocation": f"{SITE}/{INDEXNOW_KEY}.txt",
                                "urlList": urls},
                          timeout=30)
        print(f"indexnow ping ({len(urls)} urls): {r.status_code}")
    except Exception as e:
        print(f"indexnow skipped: {e}")


def write_receipt(results):
    """One line: `<utc-ts> slug=ok:<id> slug2=fail:<code>` (or a bare status)."""
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    RECEIPT.parent.mkdir(exist_ok=True)
    RECEIPT.write_text(f"{ts} {' '.join(results) if results else 'none-pending'}\n",
                       encoding="utf-8")


def add_link_comment(headers, urn, post_id, url):
    """Post the article URL as the FIRST comment. LinkedIn throttles reach on
    posts with an external link in the body, so the link lives here instead."""
    from urllib.parse import quote
    try:
        r = requests.post(
            f"https://api.linkedin.com/rest/socialActions/{quote(post_id, safe='')}/comments",
            headers=headers, timeout=30,
            data=json.dumps({"actor": urn, "message": {"text": f"Read the full post: {url}"}}),
        )
        print(f"link comment: {r.status_code}")
        return r.status_code in (200, 201)
    except Exception as e:
        print(f"link comment failed: {e}")
        return False


def share_post(headers, urn, post, url):
    """Share one post; return 'ok:<id>' or 'fail:<reason>'."""
    tags = " ".join(_hashtag(t) for t in ("MachineLearning", "DataScience", post["tag"]))
    # Link goes in the first comment (add_link_comment), NOT the body — an
    # external link in the body gets the post's reach throttled.
    commentary = f"{post['title']}\n\n{post['excerpt']}\n\n{tags}"
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
    }
    image_urn = upload_image(headers, urn, post)
    if image_urn:                                   # native image post with the branded card
        body["content"] = {"media": {"id": image_urn, "title": post["title"][:180]}}

    r = requests.post("https://api.linkedin.com/rest/posts", headers=headers,
                      data=json.dumps(body), timeout=30)
    if r.status_code in (200, 201):
        post_id = r.headers.get("x-restli-id", "n/a")
        print(f"Shared to LinkedIn (id: {post_id})")
        if post_id != "n/a":
            add_link_comment(headers, urn, post_id, url)
        return f"ok:{post_id}"
    if r.status_code == 401:
        print("LinkedIn 401: token invalid or expired (member tokens last ~60 days). "
              "Re-authorize and update the LINKEDIN_ACCESS_TOKEN secret.")
        return "fail:401-token"
    print(f"LinkedIn post failed ({r.status_code}): {r.text[:400]}")
    return f"fail:{r.status_code}"


def main():
    if not TOKEN:
        print("LINKEDIN_ACCESS_TOKEN not set; skipping LinkedIn share.")
        write_receipt(["skip:no-token"])
        return

    data = json.loads(POSTS_JSON.read_text(encoding="utf-8"))
    cutoff = (dt.date.today() - dt.timedelta(days=SHARE_WINDOW_DAYS)).isoformat()
    pending = [p for p in data["posts"] if p["date"] >= cutoff and not p.get("li_shared")]
    pending = list(reversed(pending))[:MAX_SHARES_PER_RUN]   # oldest first
    if not pending:
        print("No unshared recent posts; nothing to do.")
        write_receipt([])
        return

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": VERSION,
    }
    urn = author_urn(headers)

    results, failed, live_urls = [], False, []
    for post in pending:
        url = f"{SITE}/blog/{post['slug']}.html"
        if not wait_until_live(url):
            print(f"Article never came live ({url}); not sharing a dead link.")
            results.append(f"{post['slug']}=fail:dead-link")
            failed = True
            continue
        live_urls.append(url)
        status = share_post(headers, urn, post, url)
        if status.startswith("ok"):
            post["li_shared"] = True                # flag committed by the receipt step
            POSTS_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
        else:
            failed = True
        results.append(f"{post['slug']}={status}")

    if live_urls:
        ping_indexnow(live_urls + [f"{SITE}/blog.html", f"{SITE}/feed.xml"])
    write_receipt(results)
    print("share results: " + " ".join(results))
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
