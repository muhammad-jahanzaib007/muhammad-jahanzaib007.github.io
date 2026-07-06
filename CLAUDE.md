# jahanzaibawan.com — auto-blog + LinkedIn pipeline

GitHub Pages portfolio/blog with a fully automated posting pipeline. This
file is the ops runbook: any Claude session (laptop, claude.ai/code, mobile)
should read it before touching anything.

## Architecture

`auto-blog.yml` (crons 08:00 + 20:00 UTC = 09:00/21:00 UK BST):
1. **Generate post** (`automation/generate_post.py`) — Claude (structured
   outputs, POST_SCHEMA) or free GitHub Models. Topic queue in
   `automation/topics.json`, replenished with live demand signals (Google
   Suggest + HN). Word gate 550-1200 (retries, then hard-fails). body_html
   gate: allowed tags only, balanced markup. `image_queries` from the model
   decide body photos (Pexels, downloaded into assets/blog/body/); [] =
   text-only article — never force an irrelevant photo.
2. **Commit + push** (rebase-retry x3).
3. **Share to LinkedIn** (`post_to_linkedin.py`) — WAITS until the article
   URL returns 200 (15 min cap; requests a Pages rebuild after 5 min of
   404s — a failed Pages build once put a dead link on LinkedIn). Catch-up:
   shares any post ≤3 days old missing the `li_shared` flag (max 2/run).
   IndexNow ping after live.

## Receipts

- `.github/last-blog.txt` — ts/slug/words/title of the last generated post
- `.github/last-share.txt` — `slug=ok:<urn>|fail:<code>` per share
- `.github/linkedin-token-minted.txt` — token mint date (expires ~60 days)

## Self-healing

- `self-heal.yml`: failed Auto blog run auto-retried once; second failure →
  ONE `watchdog` issue (NEEDS A HUMAN when it greps as token/credentials).
  Backstops 08:50/20:50 UTC re-dispatch when the GitHub cron never fired.
- `watchdog.yml` (11:00 UTC daily = 12:00 UK BST): stale receipt >26h,
  `fail:` in last-share.txt, LinkedIn token ≥53 days old, latest Pages build
  failed. Auto-closes its issue when checks pass again.
- `tests.yml` runs `tests/` on every automation push.

## Hard-won rules

1. Never edit code via the GitHub web editor (smart-quote paste bricked the
   sibling YT repo's pipeline on 2026-07-05).
2. "Re-run" re-executes the run's ORIGINAL commit; push a trigger
   (`.github/blog-trigger.txt`) to test fixes instead.
3. Keep articles 550-1200 words; check word count before any manual post.
4. Body images must be genuinely relevant or absent (user feedback: generic
   tag-based photos "look so irrelevant").
5. Every page/template carries the name-entity SEO block (Jahanzaib name
   variants in keywords + JSON-LD `@id: /#person`) — keep it on new pages.
6. Cloudflare Web Analytics = manual JS beacon on every page (zone is
   DNS-only/grey-cloud; automatic injection never fires; do NOT proxy the
   zone — GH Pages SSL loop risk).
7. Deps PINNED in requirements.txt; bump deliberately.
8. Secrets only in GitHub repo secrets — never in chat, code, or files.

## Out-of-domain (needs the human)

LinkedIn token re-mint (~every 60 days; watchdog warns from day 53 — next
~2026-08-23), Anthropic/Pexels keys, domain/DNS.

## Owner context

Owner is UK-based (Leicester). Site doubles as the "genuine business"
signal for affiliate applications — keep quality high, no padded posts.

## Session log (cross-device attribution — KEEP UPDATED)

Multiple Claude sessions touch this repo (laptop, claude.ai/code web,
mobile). ANY session that changes code or makes a notable finding must
append an entry here (date, surface, branch, one-line summary) in the same
commit, so the other sessions know who did what.

- 2026-07-06 — claude.ai/code web session, branch
  `claude/pipeline-health-check-gtnyzy` (merged to main via PR #2):
  health check + audit + hardening. Closed stale watchdog issue #1
  (receipt existed again). Findings fixed: combined `git add` in
  auto-blog (per-path now), no timeout-minutes on any job (added
  everywhere), backfill/cleanup installed unpinned deps + bare `git push`
  (now requirements.txt + rebase-retry). Watchdog-time doc fix landed
  independently from both sessions the same night (main's a6aeb87 kept on
  rebase). Also verified: 2026-07-06 00:28 Pages deploy failure was a
  GitHub-side transient on a CLAUDE.md-only commit; site content
  unaffected.
