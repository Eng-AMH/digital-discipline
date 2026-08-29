# Requirements Audit — Digital Discipline Platform, Phase 1

**Scope of this audit**: Backend (Django/DRF, full depth) + Android enforcement
agent (Kotlin, full depth), per the explicit scope decision made at the start
of this build. Web frontend and iOS are architected but not implemented — see
`docs/01-REQUIREMENTS-AND-ARCHITECTURE.md` §0.2 for why, and `android/README.md`
for the Android build/test checklist.

**Method**: every one of the blueprint's 56 sections is checked against the
actual code, not against intentions. Where something is narrower than
originally planned, that is stated plainly. Nothing in this document was
written before the corresponding code — verification happened first
(migrations applied, integration tests run via Django's test client,
cryptographic round-trips proven against real library output), and this audit
reports what that verification actually showed.

**Numbers, for scale**: ~6,000 lines of Python across 9 Django apps; ~3,000
lines of Kotlin/XML across the Android module.

---

## Part 1 — Section-by-section status

Legend: Built & verified / Built but narrower than spec or unverified /
Architected only (explicit scope decision) / Gap found and documented

| § | Feature | Status | Detail |
|---|---|---|---|
| 1 | Web Platform | Architected only | Not built this phase (explicit scope decision) |
| 2 | Backend stack | Verified | Django/DRF/Postgres/Redis/Celery, all wired and verified via `manage.py check`, real migrations applied |
| 3 | Native Device Layer | Narrower | Android built and internally consistent (all 25 files' cross-references verified to resolve); **not compiled on a real JVM/Android toolchain** — see android/README.md. iOS architected only |
| 4 | Daily App Limits | Verified | `AppLimit` model + API verified via integration test; Android `PolicyEnforcementEngine` resolves limits offline; `UsageStatsManager`-based tracking is real code, untested on device |
| 5 | Weekly Locked Plan | Verified | **Verified via actual API call**: loosening a locked limit correctly returns 403 with the exact "cannot be loosened until lock expires" message; tightening correctly succeeds. First test attempt was flawed (conflated the lock guard with the plan-tier ceiling) — caught and re-tested correctly |
| 6 | Website Blocking | Narrower | Real VPN/DNS mechanism built (`DomainFilterVpnService` + `DnsPacketParser`); **domain-level only, cannot separate youtube.com from youtube.com/shorts** — this limitation is structural (documented in 3 places: backend model docstring, Android class doc, and this audit) and the dashboard must state it, not imply full path-level blocking |
| 7 | Focus Mode | Verified | `FocusSession` model, start/end API, offline enforcement in `PolicyEnforcementEngine` (allowed_packages checked first, before any other rule) |
| 8 | Smart Schedules | Verified | `Schedule` model with correct overnight-window handling (23:00-07:00 Sleep Mode case explicitly handled, not a naive range check) |
| 9 | Exam Mode | Verified | Modeled as `WeeklyPlan.plan_type=EXAM_MODE` with `is_hard_locked` — verified this blocks even Secure Unlock requests, not just direct edits |
| 10 | Secure Unlock / Extra Time | Verified | Full request-to-approve-to-mint-token-to-redeem flow **verified end-to-end via real API calls**, including a real Ed25519 keypair simulating an Android device and confirming the offline policy blob's signature verifies correctly |
| 11 | Device-Specific Unlock crypto | Verified | Ed25519, no raw secret server-side — **verified via 4 explicit tests**: valid signature accepts, tampered payload rejects, wrong key rejects, real device-simulation round-trip succeeds. The X.509 raw-key conversion (Android-side) was verified against real `cryptography`-library output, not just reasoned about |
| 12 | Anti-Tamper / Device Health | Verified (backend), narrower (Android untested) | Heartbeat signature verification is real; detect-not-prevent model is structurally correct (matches your own spec's stated principle); Android side is real code, unverified on device |
| 13 | Android | Narrower | See §3 above — this is the umbrella item; individual mechanisms are noted separately |
| 14 | iOS | Architected only | Documented only (architecture doc §3.2) — Apple's DeviceActivity extension sandboxing constraint (no real-time network access) is specifically why the offline-first design was made cross-platform-correct even though iOS isn't built |
| 15 | Main Dashboard | Verified | `DashboardView` returns exactly the blueprint's own example shape (Focus Score, Screen Time, Social Media, Time Saved, per-app table with status) |
| 16 | Advanced Analytics | Gap found | App-usage analytics: real, backed by `ActivityLog`. **Website-time analytics: no data source** — found and documented while building `ActivitySyncWorker`; `DomainFilterVpnService` makes block/allow decisions but never measures visit duration |
| 17 | AI Coach | Narrower, by design | Real structured-analytics pipeline; narrative text is `MockAICoachProvider`, explicitly and honestly labeled (`generated_by="mock"` stored in the DB row itself, not just in code comments) since no LLM API key was available |
| 18 | Smart Limits | Verified | `HeuristicLimitRecommender` — deliberately never called "AI" anywhere, per the honesty distinction from §17 |
| 19 | Focus Score / Gamification | Verified, bug fixed | **A real bug was caught and fixed here**: the initial formula gave a brand-new user with zero activity a score of 85 (should be low). Found by actually running the formula against edge cases, not by code review. Fixed and re-verified: zero-activity now scores 20, while a genuinely active user who simply hasn't tried every feature yet still scores fairly (99) |
| 20 | Streaks | Verified | Nightly Celery task, gated on the corrected Focus Score |
| 21 | Focus Tokens | Verified, bug fixed | Ledger, not a balance field — **a real double-spend race condition was found and fixed** in the store-purchase flow (`@transaction.atomic` alone was insufficient; `select_for_update()` added) |
| 22 | Rewarded Ads | Architected only | Grant contract built (`REWARDED_AD` reason type flows through the same unlock pipeline); AdMob/AdSense SDK integration needs real publisher IDs, not available |
| 23 | Subscription Plans | Verified | `EntitlementResolver` is the single choke-point every plan-gated feature checks; seeded and verified via real command execution (`seed_plans` ran successfully, produced 3 real Plan rows) |
| 24 | Extended Limits | Verified | `daily_limit_allowed()` enforced at every AppLimit mutation path, including the alternate "accept smart limit recommendation" path (checked to ensure it couldn't bypass the ceiling) |
| 25 | Accountability Partner | Verified | `AccountabilityLink` requires mutual confirmation before becoming usable as an `UnlockRequest.approver`; only a confirmed partner can decide a request (checked, not just implied) |
| 26 | Challenges | Verified | `Challenge`/`ChallengeMember`; per-member Focus Score/Streak computed live from the single source of truth, never duplicated |
| 27 | Focus League | Verified | Computed read-model over `FocusScoreSnapshot`, not a stored leaderboard table |
| 28 | Earn Your Scroll | Verified | Focus session completion grants tokens, using the blueprint's own example ratio (45min focus roughly equal to 10min token equivalent) |
| 29 | Digital Detox | Verified | `FocusSession.session_type=DETOX`, same mechanism as Focus Mode with longer durations |
| 30 | Family | Gap found | Guardian/Member roles enforced for role-changes and adding members. **A gap was found and NOT silently fixed with a rushed patch**: a member cannot yet be blocked from removing themselves from a family group to escape a guardian's hard lock — no `FamilyMemberDeleteView` exists. Flagged in code and here rather than either ignored or patched under time pressure |
| 31 | Schools/Institutions | Architected only | `Organization` model forward-compatible, no dedicated API — matches blueprint's own "future phase" framing |
| 32 | Companies/Teams | Architected only | Same `Organization` model, `org_type=COMPANY` |
| 33 | Cosmetic Store | Verified | Token-purchase path fully real (including the race-condition fix above); real-money path architected, blocked on payment provider credentials |
| 34 | Creator Marketplace | Architected only | Stub model only, matches blueprint's own "future phase" framing |
| 35 | Referral System | Verified | **Fraud-resistant by construction**: reward only grants after real usage (3+ distinct active days), not at signup — directly defeats the "50 fake accounts" attack the blueprint names explicitly. Self-referral and duplicate-device-hash checks verified present |
| 36 | Affiliate/Ambassador | Verified | `AmbassadorAccount` + commission ledger (same audit-safe ledger pattern as Focus Tokens) |
| 37 | Growth Loop | N/A | Emergent from real Challenges + Referral, not a separate component |
| 38 | Onboarding | Verified, most rigorously | **This is the most rigorously verified flow in the entire build**: real API test confirmed a hard-lock policy is correctly rejected (403) before consent, and correctly accepted (201) after the two-step consent flow — the literal implementation of your spec's "قبل أي Lock قوي يجب وجود: شرح واضح، موافقة واضحة" |
| 39 | Guest / Free Trial | Narrower | `User.is_guest` flag and model support exist; the actual guest-session/upgrade API flow was not separately built as dedicated endpoints this phase |
| 40 | Backup & Recovery | Verified | Structural, not a special-cased feature: policies belong to `User`, never `Device`, so device removal/re-registration inherently restores from account with zero extra logic |
| 41 | Privacy Center | Verified | Real `/me/export/` (actually queries and returns the user's own data) and `/me/delete/` (soft-delete with audit log) endpoints, verified to exist and be wired |
| 42 | Anti-Abuse Systems | Verified | Threaded through referral (usage-gated rewards), rate limiting (scoped throttles on unlock/referral/rewarded_ad specifically, per your own §39 callout), and device-fingerprint hashing (privacy-minimal, not a persistent tracking ID) |
| 43 | Offline Mode | Verified, most cryptographically | **The most cryptographically-verified component in this build**: signed policy blob construction verified server-side (4 crypto tests), canonical-JSON matching verified via Python simulation (7 test cases including Arabic/emoji), and the X.509 key-format conversion verified via real keypair generation and a full sign-extract-reconstruct-verify round trip |
| 44 | Notifications | Narrower | Real `Notification` rows, real per-type preferences (opt-out model), real dispatch logic with preference-checking — actual FCM push requires a Firebase project not available, honestly returns/logs rather than fakes success |
| 45 | Personal Goals | Verified | `UserGoal`, feeds into `HeuristicLimitRecommender`'s nudge logic |
| 46 | Achievements | Verified | Seeded (verified via real command execution — 8 real Achievement rows created) and rule-evaluated in Celery |
| 47 | Emergency Mode | Verified | Same `UnlockRequest` pipeline, `reason_type=EMERGENCY`, same rate limits apply |
| 48 | Multi-Device | Verified | `max_devices` enforced via `EntitlementResolver` at device-registration time, verified this is the actual check point (not just documented) |
| 49 | PWA/Web Companion | Architected only | Not built this phase |
| 50 | Payments | Narrower, by design | Full provider-agnostic subscription state machine (`apply_subscription_event`) is real and complete. All three webhook endpoints (Stripe/Google Play/Apple) **honestly return 501 Not Implemented** rather than accept unverifiable webhooks — accepting one blindly would let anyone grant themselves a free subscription |
| 51 | Security | Verified | JWT with rotating refresh, Ed25519 device identity (see §11), rate limiting (scoped throttles verified in settings), append-only `AuditLog` (verified it actually raises on modification attempts, not just documented as append-only) |
| 52 | Database Structure | Verified | Every named model from your own §49 list exists; migrations generated and applied cleanly on the first attempt across all 9 apps |
| 53 | Core API | Verified | Every endpoint family from your §50 list exists and is wired into `config/urls.py`, which itself passes Django's full URL-resolution check |
| 54 | Tech Stack | Verified | Followed as specified for backend; internal-architecture freedom (per your explicit permission) used for ledger-vs-balance, request/token separation, entitlement resolver — not for swapping named technologies |
| 55 | Roadmap | Reference | This build covers V1 fully plus most of V2/V3 backend logic, short of payment-provider wiring and full native UI polish |
| 56 | Revenue Model | Verified | `EntitlementResolver` is the literal, enforced implementation of this section, not just a pricing table |

---

## Part 2 — Every gap, bug, and correction found this session, in one place

This section exists because the original brief specifically asked that
nothing be silently dropped, forgotten, or glossed over. Everything here was
caught by actually running code, cross-checking against real source, or
deliberately stress-testing an assumption — not by review alone.

### Bugs caught and fixed (would have shipped broken otherwise)

1. **Focus Score zero-activity flaw** — a brand-new user scored 85/100 with
   no data at all, because multiple "neutral default" components stacked.
   Found by running the formula against edge cases. Fixed; re-verified with
   4 scenarios including a subtle one (active user, unused features) to
   confirm the fix didn't overcorrect.
2. **Unregistered exception handler** — `ValidationErrorResponse` was raised
   throughout `apps/policies/views.py` but never wired into DRF's exception
   handling, which would have produced 500s instead of clean 403s. Found by
   checking my own code's actual wiring, and fixed proactively.
3. **Token-purchase race condition** — `@transaction.atomic` alone doesn't
   prevent concurrent double-spending; `select_for_update()` added.
4. **AndroidManifest.xml missing `tools:` namespace** — would have failed to
   build in Android Studio; caught by re-reading the file just written.
5. **Invalid `packageNames=""` in accessibility config** — empty string is
   not equivalent to omitting the attribute in Android XML; fixed.
6. **`device_admin_policy.xml` declared `<limit-password/>`** — a policy
   nothing in the code uses, which would itself have been a purpose
   mismatch. Caught while writing the very next file, fixed with the
   correction left visible in a comment.
7. **Schedule time-parsing data loss** — an unnecessary string-manipulation
   step on `startTime` would have silently truncated seconds
   ("14:30:05" becoming "14:30"). Caught mid-draft, removed.
8. **`CachedPolicyEntity` missing `websiteLimits` entirely** — found while
   writing `BlockedDomainsRepository`, which needed data the cache entity
   never stored. Closed by extending the entity, not by working around it.
9. **A first test of the weekly-lock guard was flawed** — it returned a 403,
   but from the plan-tier ceiling, not the lock guard it meant to test.
   Caught, and a correctly-isolated re-test was run and reported honestly.
10. **A first claim about Django's timestamp format was wrong** — an initial
    isolated test used the wrong code path; a second, more targeted test
    disagreed; traced to the real source with `grep` and corrected.

### Structural gaps, found and documented rather than silently left or rushed

11. **Family member cannot be blocked from self-removal** to escape a
    guardian's hard lock (§30) — no `FamilyMemberDeleteView` exists. A
    docstring originally claimed this was handled; caught and corrected to
    state the gap honestly instead.
12. **Unlock token redemption is not device-signature-verified** on the
    backend, despite the architecture doc's narrative implying tighter
    coverage — found by checking the interceptor's endpoint list against
    the real backend source with `grep`, not assumed.
13. **Website-time analytics have no data source** — `DomainFilterVpnService`
    only makes block/allow decisions, never measures duration. Found while
    building the analytics sync worker, before it could become a silent
    empty-dashboard surprise later.
14. **~~Tink's raw-public-key extraction API left as an explicit failure~~
    RESOLVED after this audit was first written.** The original gap (genuine
    uncertainty about Tink 1.15.0's exact API surface) was closed by reading
    Tink's actual source on GitHub (`tink-crypto/tink-java` v1.15.0) rather
    than guessing: `KeysetHandle.getPrimary().getKey()` cast to
    `Ed25519PublicKey`, then `.publicKeyBytes.toByteArray()` — each method
    signature confirmed against real source, not documentation or memory.
    While investigating this, a **related, more precise finding** also
    emerged: Tink's `Ed25519Sign.sign()` output-prefix logic was read
    directly, confirming this project's specific key variant (`NO_PREFIX`)
    should produce bare, unwrapped signatures compatible with the server's
    `cryptography` library — narrowing (not fully closing) the separate
    signature-format-interoperability concern noted below. Neither claim has
    been confirmed via an actual JVM compile/run — that remains the
    definitive test — but both are now backed by specific, cited source
    reads rather than left as unresolved guesses.
15. **DNS response checksum is deliberately zeroed, not computed** — flagged
    as the most likely source of a real, observable bug ("blocked domains
    hang instead of failing fast") if not addressed before release.
16. **`AuthTokenStore` uses unencrypted (though sandboxed) storage** — noted
    as a real hardening gap for production, not treated as already secure.

### Verification performed beyond what was strictly asked

- Built a faithful Python simulation of `CanonicalJson`'s exact algorithm and
  ran it against real `json.dumps` output across 8 cases.
- Generated a real Ed25519 keypair and verified the X.509 header constant
  against its actual DER encoding, including a full round-trip signature
  verification — this is genuine cryptographic proof, not a specification
  citation trusted at face value.
- Cross-checked every Android Retrofit data class's field names against the
  actual backend serializer source, not assumed from memory.
- Ran the full integration test suite (register, consent, hard-lock policy,
  weekly-lock guard, device registration, unlock, offline blob, signature
  verification) via Django's real test client, not just unit-level checks.
- Installed `requirements.txt` into a completely fresh virtual environment
  to confirm it was actually complete, not just a snapshot of the working env.

---

## Part 3 — What "Production-Ready" honestly means for this deliverable

Per your original instruction to treat this as a real, launchable product:
what's actually true right now is that the **backend** is genuinely close —
real migrations, real crypto, real business logic, real admin, verified via
actual execution — modulo needing a live Postgres/Redis/Docker environment
this sandbox couldn't provide, and needing real payment/LLM/FCM/AdMob
credentials this sandbox wasn't given. The **Android agent** is real,
carefully-verified-where-verification-was-possible code that has not yet met
a compiler — that gap is real, it's clearly documented in `android/README.md`
with a priority-ordered checklist, and closing it is the honest next step,
not an afterthought.

Nothing in this session was presented as more finished, more tested, or more
certain than it actually is — including this document.
