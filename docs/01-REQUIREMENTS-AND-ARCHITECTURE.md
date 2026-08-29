# Digital Discipline Platform — Requirements & Architecture
### Source-of-truth: `PRODUCT BLUEPRINT` (56 sections) → this document → code

This document exists because a 56-section spec cannot be implemented directly — it must
first become unambiguous requirements, explicit OS boundaries, and a concrete data model.
**No code was written before this document.** Every section number below (§1–§56) maps to
the blueprint's own numbering.

---

## 0. Scope of this build phase

Per explicit decision: **Backend (full depth) + Android enforcement agent (full depth)**.
Web frontend (Next.js), iOS agent, and payment-provider wiring are **architected but not
implemented** in this phase — see §0.3.

### 0.1 What "full depth" means here
- Backend: every model in §49, every endpoint in §50, real business logic (policy
  resolution, unlock token cryptography, streak/score computation, referral fraud
  checks, subscription state machine) — not stubs.
- Android: a real, compilable Kotlin module using real Android APIs (`UsageStatsManager`,
  `AccessibilityService`, `DeviceAdminReceiver`/`DevicePolicyManager`, `WorkManager`,
  Room for offline cache) implementing the actual enforcement mechanism §9–10 describes.
  It cannot be *run* in this environment (no emulator/device here), so it ships with
  a build guide and must be opened in Android Studio to compile and test on a device.

### 0.2 What is explicitly deferred (and why)
| Deferred | Reason |
|---|---|
| Next.js web app (§1 Web Platform, §46 PWA) | Explicit scope decision this session |
| iOS Swift agent (§11) | Explicit scope decision this session — architecture documented in §7 below so backend contracts are iOS-ready from day one |
| Live Stripe/Play Billing/Apple IAP calls (§47) | Requires real merchant account credentials I don't have. Backend implements the full subscription state machine and webhook contract; the actual payment provider SDK call is a single swappable function. |
| AdMob/AdSense live integration (§19) | Requires real publisher IDs. Backend implements the reward-grant contract (`POST /rewards/ad-watch-verify`); client-side SDK call is a documented stub. |
| Creator Marketplace (§31), Schools (§28), Companies (§29) | Blueprint itself labels these "future"/"enterprise" phases — data model includes forward-compatible fields (e.g. `Organization` model) but no dedicated UI/API surface is built, matching the blueprint's own V4 roadmap (§52). |

### 0.3 What "Production-Ready, not Prototype" means concretely
Since I cannot deploy live infrastructure in this session, "production-ready" is
operationalized as:
1. No hardcoded secrets; all config via environment variables with `.env.example`
2. Migrations are real and reversible, not `makemigrations` left uncommitted
3. Every endpoint has permission classes, input validation, and rate limiting where the
   blueprint specifies it (§39, §48)
4. Cryptographic operations (unlock tokens, device keys) use real primitives (Ed25519 /
   HMAC via `cryptography` lib), not placeholder base64
5. Async/scheduled work (streak resets, weekly plan unlocks, AI reports) is real Celery
   task code with beat schedules, not TODO comments
6. A `docker-compose.yml` brings up Postgres + Redis + Django + Celery worker + beat
   together — this is the one part of "running" I *can* verify, since it doesn't need
   external network access beyond what's already allowlisted... actually Docker itself
   isn't installable here, so this is provided as reviewed, ready-to-run config, not
   something I executed. Flagged honestly rather than claimed as tested.

---

## 1. Product identity (strategic — for future frontend phase)

Per your input, no existing brand material exists. Since frontend isn't built this phase,
this is a **direction document**, not a design system — it exists so backend naming
(API responses, notification copy fields, error messages) is consistent with where the
brand is going, and so the eventual frontend phase starts from a decision, not a blank page.

**Working name:** *Kerno* — deliberately not "Focus," "Discipline," or "Screen Time"
(every competitor uses those words). Root suggestion: "kernel" (the control core) /
Latin-adjacent invented word, short, ownable as a wordmark, doesn't read as an English
sentence fragment. **This is a placeholder, not a locked decision** — trademark
clearance wasn't performed. The blueprint's own tagline stays:
> "You don't need less phone. You need more control."

**Anti-direction (explicit "not this"):** not a soft wellness-app palette (lavender/mint
gradients), not a dark "hacker productivity" theme, not generic SaaS blue-and-white
cards. The product enforces real limits with real consequences — the visual language
should feel more like a **precision instrument / control panel for your own attention**
than a meditation app. Typography-led rather than illustration-led. This gets fully
specified with actual type choices, color systems, and motion principles when the
frontend phase begins.

---

## 2. Requirements traceability (§1–§56 → decision)

Every blueprint section, mapped to what it becomes. "Backend" = implemented this phase.
"Android" = implemented this phase. "Architected" = data model / API contract exists,
client not built.

| § | Feature | Status | Key decision |
|---|---|---|---|
| 1 | Web Platform | Architected | API-first backend means web is a pure client of documented endpoints |
| 2 | Backend stack | **Backend** | Django/DRF kept as specified — good fit for admin, ORM, DRF permissions |
| 3 | Native Device Layer | **Android** built, iOS architected | See §7 |
| 4 | Daily App Limits | **Backend + Android** | `AppLimit` model + `UsageStatsManager` polling |
| 5 | Weekly Locked Plan | **Backend + Android** | `WeeklyPlan.locked_until`; server-enforced, device caches |
| 6 | Website Blocking | **Backend + Android** | `WebsiteLimit` + Accessibility-service URL interception (§9.2 limits) |
| 7 | Focus Mode | **Backend + Android** | `FocusSession` model + temporary policy override |
| 8 | Smart Schedules | **Backend + Android** | `Schedule` (cron-like) resolved server-side into effective policy |
| 9 | Exam Mode | **Backend** | Modeled as `WeeklyPlan` subtype with `is_locked_hard=True` + `unlock_after` |
| 10 | Secure Unlock / Extra Time | **Backend + Android** | `UnlockRequest`/`UnlockToken`, see §5 crypto design |
| 11 | Device-Specific Unlock | **Backend + Android** | Ed25519 keypair per device, see §5 |
| 12 | Anti-Tamper / Device Health | **Backend + Android** | Heartbeat endpoint + Android AccessibilityService self-check |
| 13 | Android | **Android** | Full module, see `/android` |
| 14 | iOS | Architected only | See §7 — Family Controls/DeviceActivity/ManagedSettings contract documented |
| 15 | Main Dashboard | Architected (API ready) | `GET /analytics/dashboard` returns exact shape needed |
| 16 | Advanced Analytics | **Backend** | `ActivityLog` aggregation, Celery pre-computation |
| 17 | AI Coach | **Backend** | Real LLM-call architecture (provider-agnostic interface), see §6 |
| 18 | Smart Limits | **Backend** | Heuristic recommender (documented as heuristic, not "AI", per honesty principle) |
| 19 | Gamification / Focus Score | **Backend** | Deterministic scoring function, fully specified §8 |
| 20 | Streaks | **Backend** | Celery daily job |
| 21 | Focus Tokens | **Backend** | Ledger model, not a balance field (audit-safe) |
| 22 | Rewarded Ads | Architected | Grant contract built; AdMob/AdSense SDK calls are documented stubs (§0.2) |
| 23 | Subscription Plans | **Backend** | Entitlement resolution engine, provider-agnostic (§0.2) |
| 24 | Extended Limits | **Backend** | Plan-gated validators on `AppLimit.daily_minutes` |
| 25 | Accountability Partner | **Backend** | `UnlockRequest.approver` flow + notification |
| 26 | Challenges | **Backend** | `Challenge`/`ChallengeMember` |
| 27 | Focus League | **Backend** | Leaderboard = read-model over `FocusScoreSnapshot` |
| 28 | Earn Your Scroll | **Backend** | Focus session completion → token grant → temporary limit boost |
| 29 | Digital Detox | **Backend + Android** | `FocusSession` with `session_type=DETOX`, longer durations |
| 30 | Family | **Backend** | `FamilyGroup`/`FamilyMember` with explicit consent model (§9) |
| 31 | Schools/Institutions | Architected | `Organization` model forward-compatible, no dedicated endpoints |
| 32 | Companies/Teams | Architected | Same `Organization` model, `org_type=COMPANY` |
| 33 | Cosmetic Store | **Backend** | `StoreItem`/`UserInventory`, token or IAP purchase paths |
| 34 | Creator Marketplace | Architected | `CreatorPlan` model stub only, matches blueprint's own "future" framing |
| 35 | Referral System | **Backend** | Full fraud-resistant design, §10 |
| 36 | Affiliate/Ambassador | **Backend** | `AmbassadorAccount` + commission ledger |
| 37 | Growth Loop | N/A (product mechanic, not a component) | Emerges from Challenges + Referral being real |
| 38 | Onboarding | **Backend** (API), Architected (UI) | `OnboardingState` machine on `User`, consent gates before any lock |
| 39 | Guest / Free Trial | **Backend** | Anonymous `Device` + `GuestSession`, upgrade path |
| 40 | Backup & Recovery | **Backend** | Policies belong to `User`, not `Device` — device is a *binding*, re-registration restores |
| 41 | Privacy Center | **Backend** (API), Architected (UI) | `POST /account/export`, `POST /account/delete`, data-minimization documented §11 |
| 42 | Anti-Abuse Systems | **Backend** | Threaded through referral, rewards, device registration — §10 |
| 43 | Offline Mode | **Backend + Android** | Signed policy blob, TTL-based local enforcement — §5.3 |
| 44 | Notifications | **Backend** | `Notification` model + Celery dispatch, Android receives via FCM (documented, not wired — needs Firebase project) |
| 45 | Personal Goals | **Backend** | `UserGoal` influences Smart Limits recommendation weighting |
| 46 | Achievements | **Backend** | `Achievement`/`UserAchievement`, rule-evaluated in Celery |
| 47 | Emergency Mode | **Backend + Android** | Same `UnlockRequest` pipeline, `reason_type=EMERGENCY`, hard rate-limited |
| 48 | Multi-Device | **Backend** | `Device` FK to `User`, policies resolved per-device or account-wide |
| 49 | PWA/Web Companion | Deferred | Same reason as §1 |
| 50 | Payments | Architected | See §0.2 |
| 51 | Security | **Backend** | JWT+refresh, Ed25519 device identity, rate limiting, audit log — §9 |
| 52 | Database Structure | **Backend** | Full schema, §4 |
| 53 | Core API | **Backend** | Full endpoint list, §12 |
| 54 | Tech Stack | **Backend decided** | Django/DRF/Postgres/Redis/Celery kept; justification below |
| 55 | Roadmap | Reference only | This build = V1 + most of V2/V3 backend, minus payment wiring |
| 56 | Revenue Model | **Backend** | Entitlement engine is the actual implementation of this |

---

## 3. OS-level enforcement: what is legally/technically possible

This is the most important section to get right, per your explicit instruction not to
fake this. Both platforms are covered honestly, even though only Android ships code.

### 3.1 Android — what §9/§10/§13 can actually mean

Android has **no single API called "block an app."** Real, App-Store-policy-compliant
mechanisms, in order of what this build uses:

1. **Usage measurement**: `UsageStatsManager` (needs `PACKAGE_USAGE_STATS`, a special
   permission granted via Settings, not a runtime prompt) — gives per-app foreground
   time. This is how "used 31m of 45m" is computed. **Real, used in this build.**

2. **Enforcement — foreground app interruption**: An `AccessibilityService` that
   observes window-state-changed events (which package/activity came to foreground) and,
   when a blocked/over-limit package appears, immediately launches our own
   "blocked" overlay Activity on top. This is the mechanism real published apps
   (e.g. category leaders in this space) use, and it is Play-Store-compliant **only**
   if the AccessibilityService's stated purpose in `accessibility_service_config.xml`
   and the Play Console declaration genuinely matches "helps users manage their own app
   usage" — Google has rejected apps for accessibility-permission misuse, so the
   manifest description and privacy policy must be precise. **Real, used in this build,
   with the compliance caveat documented in code comments.**

3. **Enforcement — website/URL blocking (§6)**: This is the hardest honest boundary.
   Android has no OS-level "block this URL in any browser" API for third-party apps.
   Real options, none of which is "just block the URL":
   - **VPN-based DNS/traffic filtering** (`VpnService`) — the app runs a local
     no-op VPN and filters DNS requests to blocked domains. This *is* legitimate and
     Play-compliant when disclosed, and is what this build implements for website
     blocking. **Limitation that must be stated to the user in-product**: this only
     blocks at the DNS/domain level, so it can't distinguish `youtube.com` from
     `youtube.com/shorts` (§3 Short-form Content category) — path-level blocking
     (e.g. Shorts specifically, Reels specifically) **is not possible via VPN alone**
     and is not possible at all without cooperation from the app/browser itself. The
     blueprint's own wording ("حسب إمكانيات كل نظام تشغيل" — "per each OS's
     capabilities") already anticipates this; the honest resolution is: **domain-level
     blocking, yes; in-app-feature-level blocking (Shorts specifically inside the
     YouTube app), no** — the dashboard must label this limitation explicitly rather
     than silently under-deliver.
   - Chrome-specific enterprise policies exist but require Chrome Enterprise / managed
     device enrollment, out of scope for a consumer app.

4. **"Anti-Tamper" (§9)**: The blueprint itself already draws the correct line —
   *"لا يتم التحايل على حماية Android... الـ Hard Enforcement يعتمد على صلاحيات النظام
   الرسمية"* ("we do not circumvent Android's protections; hard enforcement depends on
   official system permissions"). Concretely: we can **detect and log** that the
   AccessibilityService or VPN was disabled (via `onServiceConnected`/`onDestroy`
   lifecycle + a periodic heartbeat the backend expects) and surface "⚠ Protection
   Interrupted," but we **cannot prevent the user from disabling it** — Android
   deliberately makes accessibility/VPN services user-revocable at any time, and
   building around that would violate Play policy and this project's own stated
   principle. `DeviceAdminReceiver` can make *uninstalling the app itself* require an
   extra confirmation step, which is used, but that's the ceiling.

5. **Device Management (§10, "مع الإدارة المتقدمة")**: The blueprint correctly hedges
   this as conditional. Full device-owner-level control (can't be disabled by the user
   at all) requires **Android Enterprise / Device Owner provisioning**, which only
   applies to a device with no prior account, typically via a QR-code-based enterprise
   enrollment flow, and is realistically a **Family/School (§28) plan feature**, not
   default consumer behavior — a parent enrolling a child's device is a legitimate
   Device Owner scenario, since this can't be self-provisioned on an already-set-up
   personal phone. This build's `Device` model includes an `enrollment_type` field
   (`STANDARD` vs `DEVICE_OWNER`) so the architecture supports it, but only `STANDARD`
   (AccessibilityService + VPN) ships working code this phase.

### 3.2 iOS — architecture only, honestly bounded

Documented so the backend API contracts are correct for when iOS is built, and so no
Android-only assumption leaks into shared models.

- **Family Controls / ManagedSettings / DeviceActivity** (Apple's actual 2024+ APIs,
  matching what §11 names) are the only Apple-sanctioned path. Critically: **these APIs
  require the *authorization holder* (parent, in Family Sharing, or the device's own
  user via `AuthorizationCenter`) to explicitly grant Screen Time authorization** —
  there is no way for a third-party app to silently observe or block usage.
- **Real limitation Apple imposes** that Android doesn't: `DeviceActivityMonitor`
  extensions run in a **separate, sandboxed process** with no network access and a
  short execution budget — meaning "call our backend the moment a limit is hit" is not
  possible the way it is on Android. The realistic architecture is: the app schedules
  `DeviceActivitySchedule`/`DeviceActivityEvent` thresholds *in advance* (e.g. "warn at
  80%, block at 100%") using **on-device** `ManagedSettingsStore` shielding — the
  extension can't phone home in real time, so **offline-first is not optional on iOS,
  it's structurally required.** This build's offline-policy design (§5.3) was made
  cross-platform-correct specifically because of this constraint, even though iOS isn't
  built yet.
- **Website blocking on iOS**: `ManagedSettingsStore().shield.webDomains` gives
  Safari-only domain shielding — no VPN workaround needed, but it **only covers
  Safari**, not third-party browsers, which is a different (and differently
  communicated) limitation than Android's.

This section exists so that when iOS is built later, nobody re-derives these limits
under deadline pressure and quietly fakes something — it's decided now, while there's
no pressure.

---

## 4. Data model (§49 realized)

Full schema in `backend/core/models.py` (built next). Design decisions worth stating
before the code:

- **Policies belong to `User`, not `Device`** (§40 Backup & Recovery requirement) — a
  `Device` *binds to* and *caches* policy, it doesn't own it. Deleting/re-registering a
  device restores from account.
- **Focus Tokens are a ledger (`TokenTransaction`), not a mutable balance field** —
  required for §39 anti-abuse auditing; balance is `SUM(transactions)`, computed, never
  directly writable.
- **`UnlockRequest` and `UnlockToken` are separate models** — a *request* is the
  human/approval-workflow object (§25 Accountability Partner approves/rejects a
  *request*); a *token* is the cryptographic, device-specific, one-time, audited object
  actually presented to the device to lift a restriction (§11). Conflating them would
  make the accountability-approval flow and the cryptographic-proof flow impossible to
  reason about separately.
- **`AuditLog` is append-only and covers security-relevant events specifically**
  (unlock issuance, policy changes, device registration, tamper detection) — separate
  from `ActivityLog` (usage telemetry) and `DeviceEvent` (device lifecycle), because
  mixing "someone approved a 30-minute unlock" with "used TikTok for 4 minutes" in one
  table makes the audit trail useless.

---

## 5. Security design (§48, §51, §11)

### 5.1 Authentication
JWT access token (short-lived, 15 min) + rotating refresh token (long-lived, revocable,
stored hashed), matching §48's explicit list. 2FA via TOTP (`django-otp`), optional at
signup, **required** for `Family` admin accounts and `Accountability Partner` approval
actions specifically, since those actions gate other people's restrictions.

### 5.2 Device identity (§11 — no raw secret stored server-side)
On first registration, the **Android device generates an Ed25519 keypair locally**
(Android Keystore, hardware-backed where available) and sends only the **public key**
to `POST /devices/register`. The private key never leaves the device. Every subsequent
sensitive device action (unlock-token redemption, heartbeat) is a request **signed by
the device's private key**; the server verifies against the stored public key. This
directly satisfies "لا نخزن الـ Secret الخام في قاعدة البيانات."

### 5.3 Unlock tokens (§10, §11: device-specific, one-time, time-limited, audited)
1. User (or their Accountability Partner) approves an `UnlockRequest`.
2. Server generates a token: `{device_id, app_package, granted_minutes, issued_at, expires_at, nonce}`, signs it with a **server-held Ed25519 key**, returns the signed blob.
3. Device verifies the server's signature (server's public key is pinned in the app), checks `nonce` hasn't been seen locally (replay protection even offline), applies the temporary limit increase, and reports back `redeemed_at` on next connectivity.
4. Every issuance and redemption writes an `AuditLog` row — satisfies "كل عملية Unlock لها سجل."

### 5.4 Offline policy (§43)
Server periodically (on every policy change, and at minimum every 6h) issues a **signed
policy blob** (same Ed25519 mechanism) with an explicit `valid_until`. Device enforces
from its local signed copy and does not require live connectivity for routine
enforcement — only for *changing* the policy or redeeming new unlock tokens, exactly as
§43 specifies ("لكن العمليات الحساسة... يمكن أن تحتاج اتصالًا بالسيرفر").

---

## 6. AI Coach (§17, §18) — honesty on "AI"

Two genuinely different things the blueprint calls "AI," kept architecturally distinct
so neither is faked as the other:

- **§18 Smart Limits ("recommend 35 min/day")**: implemented as a **deterministic
  heuristic** (percentile of the user's own trailing 14-day usage, nudged toward the
  category median from opted-in aggregate data, clamped to plan limits). This is *not*
  an ML model — calling it one would be dishonest. Documented in code as
  `HeuristicLimitRecommender`.
- **§17 AI Coach weekly narrative report**: this is a genuine natural-language
  generation task (turning structured analytics into "Your biggest usage period was
  9 PM–11 PM... try a 45-minute Focus Session tomorrow") — this is architected as a
  provider-agnostic `AICoachProvider` interface with the actual prompt template and
  structured-input contract built, calling out to an LLM API. **No API key is
  configured in this build** (none provided), so it ships with a `MockAICoachProvider`
  that uses the same interface with template-based text — this is clearly labeled as a
  development fallback in code, not presented as the real feature.

---

## 7. Subscriptions & entitlements (§20, §23, §24, §56)

Rather than scatter `if user.is_pro` checks through the codebase, this is one
**`EntitlementResolver`** service: given a `User`, returns a typed `Entitlements`
object (`max_devices`, `weekly_lock_available`, `ai_coach_available`,
`max_daily_limit_minutes`, `ads_enabled`, ...). Every feature checks entitlements
through this single resolver — this is what makes §23's plan table (Free/Pro/Family)
enforceable consistently and auditable, and it's also the extension point for §31/§32
(Schools/Companies) later without a rewrite.

Subscription **state** (`ACTIVE`, `GRACE_PERIOD`, `CANCELED`, `EXPIRED`) is owned by our
backend regardless of which storefront (Web/Google Play/Apple) originated it, matching
§47's explicit "Backend هو مصدر الحقيقة." The provider-specific webhook handlers
(`stripe_webhook`, `play_billing_webhook`, `apple_iap_webhook`) all funnel into the same
`apply_subscription_event()` — only the webhook signature verification differs per
provider, and only that verification code is unbuilt (needs real credentials).

---

## 8. Gamification scoring (§19) — made deterministic and explicit

The blueprint lists Focus Score inputs but not a formula — leaving it undefined would
mean the number is arbitrary. This build defines it explicitly (tunable via constants,
not hardcoded magic numbers scattered in code):

```
FocusScore (0-100) =
    40 * limit_adherence_rate        (respected limits / total limits, 7-day window)
  + 25 * focus_session_completion    (completed / started focus sessions, 7-day window)
  + 15 * consistency_bonus           (days active with ≥1 tracked policy / 7)
  + 10 * night_usage_penalty_inverse (1 - (late-night minutes / total minutes), floored at 0)
  + 10 * weekly_plan_respect         (1 if current WeeklyPlan never breached, else partial credit)
```
Computed nightly via Celery, stored as `FocusScoreSnapshot` (time-series, not
overwritten) — required for §27 Focus League history and §16 trend display.

---

## 9. Consent & onboarding gates (§38, §30, §51-adjacent — safety, not just UX)

The blueprint itself states this requirement explicitly: *"قبل أي Lock قوي يجب وجود:
شرح واضح، موافقة واضحة، توضيح الصلاحيات، إمكانية معرفة ما الذي سيحدث."* This is
implemented as a **hard backend gate**, not just a frontend screen that could be
skipped: `POST /policies` for any policy with `enforcement_level=HARD_LOCK` returns
`403` unless `User.onboarding_state.permissions_explained_at` and
`.consent_given_at` are both set, checked server-side. For `FamilyGroup` specifically,
a **minor member cannot self-remove a policy their guardian set** — enforced by
`FamilyMember.role` permission checks — but a family admin *can* always be reached and
can always adjust, matching the blueprint's "care not punishment" philosophy (§56) and
avoiding a design where a minor is locked out with no recourse.

---

## 10. Anti-abuse (§39, §35, §36)

Threaded requirement, not a bolt-on module:
- **Referral**: reward grants only on the *referred* user's device reaching a **real
  usage threshold** (e.g., 3 distinct days with logged `ActivityLog` data) — not on
  signup — which structurally blocks the "create 50 empty accounts" attack the
  blueprint names explicitly.
- **Device fingerprint**: derived from the Ed25519 public key + install-time signals,
  never a persistent cross-app tracking identifier — this is a data-minimization choice
  consistent with §41 Privacy Center, not just an anti-fraud one.
- **Rate limits**: DRF throttle classes on `/unlock/*`, `/referral/*`,
  `/rewards/ad-watch-verify` specifically (the three blueprint explicitly flags in §39).
- **Reward cooldowns**: `TokenTransaction` reason codes make "5 ad-watches in 2 minutes"
  detectable and rate-limited, not just loggable after the fact.

---

## 11. What "Requirements Audit" will mean at the end

Per your closing instruction, after backend + Android are built, I will produce
`docs/03-REQUIREMENTS-AUDIT.md` — a section-by-section (§1–§56) checklist against this
document and the actual code, explicitly calling out anything that turned out to be
narrower than planned once real implementation surfaced constraints (rather than
silently shipping a gap).

---

## 12. Tech stack — final decision + justification (§54)

| Layer | Blueprint said | Decision | Why |
|---|---|---|---|
| Backend framework | Django + DRF | **Kept** | Admin panel alone is worth it for a policy/subscription-heavy domain; DRF permission classes map cleanly onto the entitlement model |
| Database | PostgreSQL | **Kept** | Relational integrity matters here (policies, tokens, ledgers) — this is not a document-shaped domain |
| Cache/broker | Redis | **Kept** | Needed for Celery + rate limiting + heartbeat freshness checks |
| Async | Celery + beat | **Kept** | Streak resets, weekly unlocks, AI reports, achievement evaluation are all genuinely scheduled/background work |
| Realtime | WebSockets (Django Channels) | **Kept, narrowed** | Used specifically for live Device Health status and Focus Session countdown — not force-fit everywhere |
| Android | Kotlin | **Kept** | Only viable choice for AccessibilityService/VpnService/DeviceAdmin |
| Crypto | (unspecified) | **`cryptography` (Python) / Android Keystore + Tink (Kotlin)**, Ed25519 | Real asymmetric primitives, not a custom scheme |

No deviation from the blueprint's stack was needed for the in-scope layers — the
freedom granted is used instead on **internal architecture decisions** (ledger vs
balance, request/token separation, entitlement resolver) where the blueprint didn't
specify implementation, not on swapping named technologies.

---

**Next**: `docs/02-DATA-MODEL.md` (full schema) → `backend/` implementation → `android/`
implementation → `docs/03-REQUIREMENTS-AUDIT.md`.
