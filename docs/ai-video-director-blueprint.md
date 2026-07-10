# AI Video Director — Product Blueprint & Technical Plan

Status: PLANNING (no code yet). Branch: `claude/ai-video-director-app-3ycq25`.
Owner ask (2026-07-10): analyse, audit, structure the app; decide stack, DB,
architecture; do NOT build yet.

---

## 1. Product definition

**One-liner:** An AI director for people who want to start content creation
but don't know how to shoot video. The user brings an idea (or a script, or
both) and optionally a photo of their recording space; the app returns a
complete, scene-by-scene shooting plan they can follow like a recipe.

**Inputs (any combination — the app fills the gaps):**
1. Topic/idea only → AI writes the script.
2. User's own script → AI structures it into scenes.
3. Script + preferences (tone, length, platform) → AI plans around them.
4. Optional: photo(s) of the recording environment → AI critiques lighting,
   background, clutter, color and suggests concrete fixes ("move the lamp
   camera-left, warm bulb, close the curtain behind you").
5. Optional: a photo of the user → used in storyboard frames.

**Output — the "Director's Plan":**
- Full script with per-scene dialogue.
- Scene list with timestamps (e.g. 00:00–00:12 hook, 00:12–00:45 point 1…).
- Per scene: shot type (close-up / medium / wide), camera height & angle,
  camera distance, subject position in frame, posture (sitting/standing/
  walking/gesturing), lighting setup, B-roll suggestions.
- **A storyboard frame per scene**: a visual mock showing the user's own
  background with the subject placed and framed as the shot requires —
  so a total beginner can literally match their camera to the picture.
- Environment fix list (from the photo critique).
- Exportable as a one-page shot list (PDF) + teleprompter mode for dialogue.

**Target user:** absolute-beginner creators (talking-head YouTube/TikTok/
Reels/educational content). Not an editor, not a camera app — a *pre-
production director*.

---

## 2. Feature scope (MoSCoW)

| Priority | Feature |
|---|---|
| MUST | Idea→script generation; own-script import; scene breakdown with timestamps, dialogue, camera, posture, lighting per scene |
| MUST | Storyboard frame per scene (background + posed subject + framing guides) |
| MUST | Environment photo critique (vision) with actionable fixes |
| MUST | Project save/load on device; shot-list export (PDF/print) |
| SHOULD | Teleprompter mode; platform presets (YouTube 16:9, TikTok/Reels 9:16); re-generate a single scene; multi-photo environment analysis |
| COULD | Photorealistic AI-rendered storyboard frames (image-gen); user photo compositing; voice input of the idea; multi-language scripts |
| WON'T (v1) | Video recording/editing; team collaboration; auto-upload to platforms |

---

## 3. The storyboard problem — the key technical decision

The ask is "a demo screenshot of each scene with the user's background and
the user in it." Two ways to produce that:

**A. Programmatic composition (deterministic, recommended for v1).**
The AI returns *structured placement data* per scene (subject position,
scale, pose id, shot type, camera height/angle, lighting direction). The
app renders the frame itself on a canvas/SVG:
- the user's background photo, cropped to the platform aspect ratio and to
  the shot type (close-up = zoomed crop, wide = full photo);
- a posed human silhouette/mannequin from a pose library (sitting, standing,
  gesturing, walking — ~12 poses cover talking-head content), placed and
  scaled per the AI's data;
- overlays: rule-of-thirds grid, headroom/eyeline guides, arrows for
  camera height/angle, a small top-down camera-position diagram, lighting
  direction icons.
Pros: zero extra cost, instant, never "hallucinates" a wrong room, works
offline after generation, fully consistent with the plan data. Cons: looks
schematic, not photorealistic — but for the job ("match your camera to
this") schematic is arguably *better* than photoreal.

**B. AI image generation (v2 upgrade, optional per-frame).**
img2img on the background photo (e.g. Gemini image API / Stability) prompted
from the scene spec, optionally with the user's face/reference photo.
Pros: wow factor. Cons: cost per frame, latency, inconsistency between
frames, hallucinated room changes, identity/likeness handling, and a second
vendor dependency.

**Decision: A for MVP, B as a paid "HD storyboard" toggle later.** The data
model (§6) stores placement data, so B can be layered on without rework.

---

## 4. Architecture

```
┌────────────────────────────── Client (one codebase) ─────────────────────────────┐
│  React + TypeScript + Vite PWA                                                   │
│  ├─ Wizard UI (idea → script → scenes → storyboard)                              │
│  ├─ Storyboard renderer (Canvas/SVG compositor + pose library)                   │
│  ├─ Teleprompter / export (PDF via client-side lib)                              │
│  └─ Local store: IndexedDB (Dexie) — projects, photos, plans                     │
│         Capacitor wrapper → iOS / Android;  same PWA installable on desktop      │
└───────────────────────────────────┬──────────────────────────────────────────────┘
                                    │ HTTPS (no API keys on the client, ever)
┌───────────────────────────────────▼──────────────────────────────────────────────┐
│  Cloudflare Worker — thin AI proxy                                               │
│  ├─ /api/script      → Claude: idea/script → script + scene breakdown            │
│  ├─ /api/analyze-env → Claude vision: photo critique (base64 image in)           │
│  ├─ /api/storyboard  → Claude: scene → placement/lighting/camera JSON            │
│  ├─ Streaming (SSE passthrough), rate limiting (per-IP + turnstile),             │
│  │   input caps, JSON-schema-validated responses                                 │
│  └─ Secrets: ANTHROPIC_API_KEY in Worker env (never client-side)                 │
└───────────────────────────────────┬──────────────────────────────────────────────┘
                                    │
                       Anthropic API (claude-opus-4-8)
                       structured outputs + vision + streaming

Later (accounts/sync/payments): Supabase (Auth + Postgres + Storage) slots in
behind the Worker without touching the client data model (local-first sync).
```

**Why no traditional backend/DB at v1:** everything the app produces belongs
to one user and fits on their device. Local-first (IndexedDB) means zero
hosting cost, offline access to saved plans, no auth to build, no PII stored
server-side (environment/user photos never persist on the server — they pass
through the Worker to the vision API and are discarded). Cloud sync is an
additive later step, not a foundation to lay now.

---

## 5. Tech stack & rationale

| Layer | Choice | Why |
|---|---|---|
| UI | React 18 + TypeScript + Vite | Largest ecosystem, fast dev, easy hiring/handoff; TS matters because the whole app revolves around a typed scene schema |
| Styling | Tailwind CSS | Fast iteration, consistent mobile-first design |
| Mobile/desktop | PWA first → Capacitor for App Store/Play Store | One codebase for web + iOS + Android + installable desktop. Avoids React Native/Flutter rewrite; the app is UI+canvas, not sensor-heavy, so web tech is fully sufficient |
| Storyboard render | HTML Canvas (or SVG→canvas) + curated SVG pose library | Deterministic compositor per §3A; exportable to PNG per frame |
| Local data | IndexedDB via Dexie.js | Structured queries over projects/scenes; handles photo blobs |
| PDF export | `pdf-lib` or browser print CSS | Client-side, no server |
| AI proxy | Cloudflare Workers | Owner already runs Cloudflare (site analytics/DNS); generous free tier (100k req/day); global edge; secrets management; SSE streaming support |
| AI model | `claude-opus-4-8` — structured outputs (`output_config.format` JSON schema), vision, adaptive thinking, streaming | One model does script-writing, scene direction, and photo critique; structured outputs guarantee parseable scene JSON (no regex parsing) |
| DB (phase 3+) | Supabase (Postgres + Auth + Storage) | Free tier, row-level security, easiest path to accounts/sync/payments |
| Payments (later) | Stripe or LemonSqueezy | LemonSqueezy simpler for solo dev (merchant of record, handles VAT) |
| Repo/CI | Dedicated new GitHub repo (recommended) + GitHub Actions | Keep this portfolio/blog repo's automation untouched; Worker deploys via `wrangler`, PWA via Pages/Cloudflare Pages |

**Explicitly rejected:**
- *React Native / Flutter*: native rewrite cost with no benefit — no camera-
  hardware features in v1 (photo upload is `<input capture>`, which PWAs do).
- *Client-side Anthropic key* (works via `anthropic-dangerous-direct-browser-
  access`): fine for a personal tool, unshippable for a public app — key
  theft = unbounded bill. The Worker proxy is non-negotiable.
- *Electron*: unnecessary; installable PWA covers desktop.
- *Building storyboards with image-gen at v1*: §3.

---

## 6. Data model (client-side, Dexie tables)

```ts
Project   { id, title, createdAt, updatedAt, platform: '16:9'|'9:16'|'1:1',
            targetLengthSec, tone, status }
ScriptDoc { id, projectId, source: 'ai'|'user'|'hybrid', fullText, version }
EnvPhoto  { id, projectId, blob, width, height, analysis?: EnvAnalysis }
EnvAnalysis { lightingScore, issues: [{severity, issue, fix}],
              strengths: string[], overallVerdict }
Scene     { id, projectId, index, tStartSec, tEndSec, purpose,          // "hook"
            dialogue, deliveryNotes,                                    // what+how to say
            shot: { type: 'CU'|'MCU'|'MS'|'WS', cameraHeight: 'eye'|'high'|'low',
                    cameraAngle: 'front'|'34L'|'34R'|'profile', distanceM },
            subject: { pose: PoseId, posXPct, posYPct, scalePct,
                       facing, action },                                 // renderer input
            lighting: { keyDirection, notes },
            broll?: string[],
            frame?: { pngBlob }                                          // rendered storyboard
          }
```

The `Scene.shot/subject/lighting` object **is** the JSON schema the AI must
return (strict structured outputs) — the renderer consumes it directly.
This schema is the contract of the whole product; it gets designed and
frozen first.

---

## 7. AI pipeline design

Three Worker endpoints, three focused prompts (not one mega-prompt):

1. **Script & scene breakdown** — input: idea|script + platform + length +
   tone (+ env analysis summary if available, so direction matches the real
   room). Output (strict schema): full script + `Scene[]` with all direction
   fields. Streaming for perceived speed; word/duration budget enforced in
   schema + validated server-side.
2. **Environment critique (vision)** — input: photo (base64, downscaled
   client-side to ≤1568px to cap tokens). Output: `EnvAnalysis`. Explicitly
   prompted to give *physically actionable* fixes (move/turn on/close/hang),
   not gear-shopping advice, and to say when the room is already fine
   (echoes the blog lesson: never force irrelevant suggestions).
3. **Scene refinement** — regenerate/adjust a single scene ("make this one
   standing", "shorter dialogue") without re-running the whole plan.

Cost model (rough, opus-4-8 at $5/$25 per MTok): a full 10-scene plan ≈
3–6k tokens out ≈ **$0.10–0.20 per project**; photo critique ≈ $0.02–0.05.
Cheap enough for a free tier with per-IP rate limits; paid tier later lifts
limits and adds HD storyboards.

Guardrails in the Worker: max input sizes, schema validation of every AI
response before it reaches the client, per-IP daily quota (KV counter),
Cloudflare Turnstile on generate endpoints to stop bot drain.

---

## 8. Security & privacy

- API keys only in Worker secrets (mirrors repo rule 8: secrets never in
  code/chat/files).
- Photos: processed in-memory, never stored server-side; stored locally on
  the user's device only. State this in the privacy note — it's a selling
  point.
- No accounts in v1 ⇒ no credential surface at all.
- When Supabase lands: RLS on every table, photos in private buckets.

---

## 9. Roadmap

| Phase | Deliverable | Scope |
|---|---|---|
| 0. Contract | Frozen `Scene` JSON schema + 3 prompt drafts + 5 golden test fixtures (idea→expected plan shape) | The spine; everything else builds on it |
| 1. Pipeline MVP | Worker deployed with the 3 endpoints, rate-limited, schema-validated; testable via curl | Proves quality of direction output before any UI |
| 2. App MVP | PWA: wizard (idea/script → plan), scene cards with all direction data, env-photo critique, local save, PDF shot list | Usable product, schematic frames not yet composited |
| 3. Storyboard renderer | Canvas compositor + pose library + framing overlays + per-scene PNG export | The differentiator |
| 4. Polish & ship | Teleprompter, platform presets, install prompts, Capacitor builds → Play Store/App Store, landing page | Public launch |
| 5. Growth (post-launch) | Supabase accounts+sync, payments, HD (image-gen) storyboards, multi-language | Driven by usage |

Each phase is independently verifiable (golden fixtures for 0–1, e2e flows
for 2–4) — no big-bang integration.

---

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| AI direction is generic/wrong (the product IS the quality of direction) | Phase 0 golden fixtures reviewed by owner before UI work; prompts encode real cinematography rules (shot grammar, 180° rule, eyeline, headroom) rather than "be a director" |
| Storyboard frames look toy-like | Lean into "technical blueprint" aesthetic (guides, labels, diagrams) rather than imitating photos badly; HD image-gen as later upsell |
| API cost abuse on a public endpoint | Turnstile + per-IP KV quotas + hard input caps from day one |
| Scope creep toward video editing | WON'T list in §2; the product ends where recording begins |
| Solo-dev bandwidth | Phasing above; each phase ships something usable; this repo's blog automation stays untouched (separate repo) |
| App-store friction with Capacitor-wrapped PWA | Ship web/PWA first (no gatekeeper); stores are phase 4, with native niceties (haptics, share sheet) added to pass review |

---

## 11. Delivery plan — how I'd lead the build

Build-time multi-agent split (when the owner says "go"):

- **Agent A — AI pipeline:** Phase 0+1. Schema, prompts, Worker, fixtures.
  Highest-risk, starts first, everything downstream consumes its contract.
- **Agent B — App shell:** Phase 2 UI against a mocked pipeline (fixtures
  from A double as mocks), so A and B run in parallel.
- **Agent C — Renderer:** Phase 3 compositor, developed against the frozen
  schema with fixture data; pure client-side, fully parallelizable.
- **Lead (me):** owns the schema contract, reviews merges, runs e2e
  verification per phase, keeps the golden-fixture suite green in CI.

Sequencing rule: nothing merges that changes the Scene schema after Phase 0
without a versioned migration. Definition of done per phase = fixtures/e2e
pass + owner sign-off on output quality (esp. Phase 0).

**Decisions needed from the owner before build starts:**
1. New dedicated repo (recommended) vs. a folder in this repo?
2. Platform priority: web-first launch (recommended) vs. stores-first?
3. Free-only MVP vs. payments wired in from the start?
4. Budget comfort for API costs during the free period (~$0.15/project)?
