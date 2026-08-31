# jahanzaibawan.com — auto-blog + LinkedIn pipeline

GitHub Pages portfolio/blog with a fully automated posting pipeline. This
file is the ops runbook: any Claude session (laptop, claude.ai/code, mobile)
should read it before touching anything.

**Keep replies TERSE** (owner ask, 2026-07-08): answer, state the action,
done — no walls of text, no restating what the owner knows. Conserves tokens.

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
  (The 08:50/20:50 slot backstops were RETIRED 2026-07-11 — the external
  heartbeat Worker covers missed slots; see the YT repo's 2026-07-08 call.)
  Every invocation also re-runs the latest Pages build if it failed —
  GitHub Pages throws intermittent "Deployment failed, try again later"
  transients (4x on 2026-07-06); a re-run of the same artifact clears them.
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

- 2026-08-31 - laptop Claude Code session (direct commit to main, d695aac):
  Auto blog had failed every run since 2026-08-30 08:00 with an Anthropic
  400, "credit balance is too low". Claude was the only live provider
  (GitHub Models retired since July) and the error raised straight out of
  _raw_completion, killing the run. Owner rule is free services only, so
  Gemini 2.5 Flash free tier now leads the chain (same provider and
  key-rotation as ai-tools-yt generate_brief.py), _gemini_schema() strips
  additionalProperties for Gemini's responseSchema, and the Claude call is
  wrapped so a dead key falls through instead of failing the run. 9/9
  tests. BLOCKED until the GEMINI_API_KEY secret is added to this repo.
  Also open: LinkedIn token minted 2026-07-01 expires ~2026-08-30
  (watchdog issue #10), last successful share 2026-08-29.

- 2026-07-05/06 — laptop Claude Code session (direct commits to main):
  pinned requirements.txt + auto-blog installs from it, tests/ +
  tests.yml, self-heal.yml (retry-once + 08:50/20:50 backstops +
  needs-human classification), runbook. Requested the Pages rebuild that
  cleared the 00:27 failed deploy ("built no error").
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
- 2026-07-06 — claude.ai/code web session (same as above): second Pages
  deploy failure at 01:30 UTC (15ce7de), identical "Deployment failed,
  try again later" transient; re-run of the failed job went green in ~30s.
  Pattern: both failures tonight hit deploys fired ~4-6 min after a
  successful deploy — likely GitHub throttling rapid back-to-back Pages
  deployments. If it recurs: just re-run the failed run (safe here — the
  deploy re-runs its own commit, which IS the intended content); no code
  change needed.
- 2026-07-06 — claude.ai/code web session (same as above): throttling
  theory REVISED — a third deploy failure (46d2c2f, 01:35) also failed on
  re-run 9 min after a success, so this is an intermittent GitHub-side
  Pages incident, not just back-to-back throttling. Permanent mitigation
  shipped: self-heal.yml now re-runs the latest failed Pages build on
  every invocation, and watchdog.yml heals-then-alerts (re-run + 90s
  re-check before opening an issue). The managed pages workflow can't be
  patched or watched via workflow_run, so scheduled re-kicks are the
  strongest fix available short of migrating Pages to a repo-owned deploy
  workflow (build_type=workflow) — do that only if transients keep
  recurring across days.
- 2026-07-06 09:45 — claude.ai/code web session (same as above): GitHub
  silently ate BOTH morning crons (08:00 Auto blog AND the 08:50
  self-heal backstop — the backstop is itself a cron, so it cannot catch
  a morning where GitHub's scheduler is down wholesale). Recovered by
  manual workflow_dispatch at 09:46; post + LinkedIn share landed by
  09:53, receipts fresh. The 09:44 Pages deploy transient also recurred
  and was cleared by re-run. If a whole morning goes quiet again: check
  the Actions tab for missing scheduled runs and dispatch auto-blog.yml
  by hand; only the human-visible watchdog issue (or a session doing a
  health check) catches a full scheduler outage.
- 2026-07-10 — claude.ai/code web session (branch
  claude/pipeline-health-check-gtnyzy): LinkedIn reach fix. Tried moving the
  article link to the first comment (body links get reach-throttled), but the
  comment-create API returns 403 — LinkedIn gates programmatic commenting
  behind the Community Management API, and pinning has NO API. Reverted to
  link-in-body (at the end) so posts stay auto-clickable; max-reach requires
  the owner to add+pin a comment by hand. NOTE the 2026-07-09 11:07 post
  (augmentation-that-leaks) shipped during the broken window with NO link —
  add manually if wanted. Groups auto-posting is also impossible (no API).
- 2026-07-11 ~23:30 — laptop Claude Code session (direct commit to main):
  DUPLICATE POSTS diagnosed and fixed. Since the heartbeat's write path came
  alive (2026-07-10), every slot got covered twice: the Worker dispatched
  ~35-40 min after slot time, then GitHub's late cron ALSO ran (no dedupe
  here — only the YT repo had a precheck). Result: 2 posts + 2 LinkedIn
  shares per slot on 07-10 evening, 07-11 morning AND 07-11 evening (6
  duplicate posts total; owner may want to prune the extra posts/shares).
  Fix: ported the YT repo's deterministic precheck to auto-blog.yml (a
  scheduled run skips itself when ANY other auto-blog run was created
  at/after its slot time) and retired self-heal.yml's 08:50/20:50 slot
  backstops (redundant with the heartbeat, and one more duplicate path —
  the YT repo retired its own on 2026-07-08).
- 2026-07-11 ~23:55 — laptop Claude Code session (same): SINGLE FIRING
  SOURCE cutover — `schedule:` crons REMOVED from auto-blog.yml (mirrors the
  YT repo, same commit-night). The heartbeat Worker is now the only
  scheduled trigger for this pipeline (dispatches 08:00/20:00 UTC exactly,
  retries via :20/:40 sweeps). Precheck stays as a dead-code safety net.
  Never re-add crons here — the cron-vs-Worker race is what double-posted
  every slot on 2026-07-10/11.
- 2026-07-17 — laptop Claude Code session (direct commit to main): ported a
  conflict-recovery fix from the YT repo (where it had failed a publish that
  day). Both push loops (post-commit + share receipt) did a plain `git pull
  --rebase` that, on a conflict in a pointer/ledger file (posts.json,
  feed.xml), left a stuck rebase whose "unmerged files" state failed every
  later retry. Now `git pull --rebase -X theirs` (keeps this run's post) with
  `git rebase --abort` before retrying; 3→5 attempts. Same-day twin-repo fix
  per the rule that a fix to one of a twin-pipeline pair must be checked
  against the other. No live blog failure had hit this yet — pre-emptive.
