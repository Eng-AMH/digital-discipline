# Kerno Android — Build & Test Guide

## Honest status (read this first)

This is real, complete Kotlin code using real Android APIs — not a prototype
or a UI shell. It has **not been compiled or run** in the environment this was
built in (no Android SDK, emulator, or device was available). Opening it in
Android Studio is the first thing that needs to happen, and it will very
likely surface small issues (import ordering, a Gradle version mismatch, a
Kotlin API that shifted between versions) that only a real compiler catches.
None of that should be surprising, and none of it reflects on whether the
underlying *design* is sound — the crypto layer specifically was checked
against real, working ground truth (see below) precisely because it couldn't
be checked by compiling and running it.

## Build steps

1. Open `android/` as a project in Android Studio (Ladybug 2024.2.1+
   recommended, for Kotlin 2.0/KSP 2.0 compatibility).
2. Let Gradle sync. `compileSdk 35` / AGP `8.7.3` requires a reasonably recent
   Android SDK Platform 35 installed via SDK Manager.
3. `./gradlew assembleDebug` from the `android/` directory, or the Studio
   equivalent.
4. Point `debug` builds at a running instance of the backend built this
   session (`cd ../backend && python manage.py runserver`) — the emulator's
   `10.0.2.2:8000` default in `app/build.gradle`'s `buildConfigField` assumes
   this. A real device on the same network needs the host's actual LAN IP.

## Verification checklist, in priority order

These are every item flagged inline throughout the codebase as "needs real
device testing," consolidated here so nothing gets lost in code comments.

### 1. `CanonicalJson` (data/crypto/CanonicalJson.kt) — HIGH PRIORITY
The single most safety-critical file: if this produces byte-different output
than the server's `json.dumps(sort_keys=True, separators=(",",":"))`, **every
signature verification silently fails**. Verified via a faithful Python
simulation of the exact algorithm (see this build session's history) across
key-sorting, nested objects, arrays, Arabic text, and emoji surrogate pairs —
all matched real `json.dumps` output. Not yet verified by compiling and
running this actual `.kt` file. **Test**: log the canonical string this
produces for a real device-signed heartbeat payload, and independently verify
in a Python shell that `json.dumps(same_dict, sort_keys=True,
separators=(',', ':'))` produces an identical string.

### 2. Ed25519 Keystore generation (data/crypto/DeviceKeyManager.kt) — HIGH PRIORITY
Two specific unverified assumptions:
- `Signature.getInstance("Ed25519")` against a Keystore key generated via
  `ECGenParameterSpec("ed25519")` — if this throws
  `NoSuchAlgorithmException`/`InvalidKeyException` on your target API level,
  try `"EdDSA"` as the algorithm string instead (used in some JCA provider
  docs) and report which one actually works, so this comment can be corrected.
- `isHardwareEd25519Available()`'s probe-based detection — confirm this
  correctly identifies both hardware-Ed25519-capable devices (e.g. newer
  Pixels) and devices that need the Tink software fallback (e.g. older/budget
  Android 8-10 devices, which is most of this app's minSdk-26 addressable range).

### 3. X.509 header for raw <-> wrapped Ed25519 key conversion (DeviceKeyManager +
   PolicyBlobVerifier) — VERIFIED, lower priority
The 12-byte header constant was checked against a real Ed25519 keypair's
actual X.509 DER encoding (generated via the same `cryptography` library the
backend uses), including a full extract -> reconstruct -> verify-a-real-signature
round trip. This is the one crypto claim in this codebase backed by genuine
cryptographic ground truth rather than simulation or specification citation.
Still worth a real-device sanity check, but this is not where I'd expect a bug.

### 4. Tink fallback signer public-key extraction — RESOLVED
`TinkBackedSigner.publicKeyBytes()` was an explicit `NotImplementedError` as of
the initial build. **This has since been resolved** by reading Tink 1.15.0's
actual source on GitHub (not guessing): `KeysetHandle.getPrimary()` ->
`Entry.getKey()` cast to `Ed25519PublicKey` -> `.publicKeyBytes` ->
`.toByteArray()`, with each method's exact signature confirmed against the
real `tink-crypto/tink-java` v1.15.0 source (`KeysetHandle.java`,
`Ed25519PublicKey.java`, `util/Bytes.java`). Still not compiled/run on a real
JVM, so this remains on the checklist, but it is no longer an unresolved
guess — it's traceable to specific, cited lines of the real library.

### 4b. Tink <-> `cryptography` signature format interoperability — STILL UNVERIFIED
Separate concern from 4 above, and still genuinely open: whether Tink's
Ed25519 signing/verification produces/consumes the standard raw 64-byte
RFC 8032 signature format with no Tink-specific wrapping (e.g. a key-ID
prefix, which some Tink signature schemes add depending on `Variant` —
this project's template uses `NO_PREFIX` per
`Ed25519PublicKey.create(publicKeyBytes)`'s default call in the real source,
which is a good sign but was not independently re-confirmed for the
*signature* output format specifically, only the *public key* format). If
signatures produced by a Tink-fallback device fail server-side verification
while hardware-Keystore-backed devices succeed, this is the first place to
check.

### 5. DNS packet parsing (enforcement/DnsPacketParser.kt) — HIGH PRIORITY, HIGH RISK
Raw binary protocol code. A bug here doesn't fail gracefully — it can silently
break **all** internet connectivity on the device, not just website blocking.
Specifically needs:
- A packet capture (Wireshark on a rooted test device, or Android Studio's
  Network Profiler) of real DNS queries, to confirm the IPv4/UDP/DNS header
  offsets are being read correctly.
- Confirmation that normal (non-blocked-domain) browsing is **completely
  unaffected** — this matters more than confirming blocking works, since a
  parsing bug is far more likely to break unrelated traffic than to fail to
  block a domain.
- IPv6 (AAAA query) handling — currently parsed identically to A queries;
  confirm this is actually correct for apps/browsers that prefer IPv6.
- **The UDP checksum gap is real and explicitly unresolved** in
  `buildNxDomainResponse` — currently zeroes the checksum (valid per RFC 768,
  but some network stacks may not accept it). If blocked domains "hang"
  instead of failing fast with an error, this is the first place to look.

### 6. Accessibility service reliability across OEM skins
`AppBlockAccessibilityService` uses the standard, documented
`TYPE_WINDOW_STATE_CHANGED` pattern, but some OEM Android skins (certain
Xiaomi/MIUI, Huawei, some Samsung battery-optimization modes) are known in the
broader Android developer community to kill background accessibility services
more aggressively than stock Android. Test on at least one heavily-skinned
OEM device, not only a Pixel/stock emulator.

### 7. Unlock token redemption is NOT device-signature-verified
Documented in `DeviceSigningInterceptor`'s doc comment as a deliberate,
flagged gap (found by cross-checking against the actual backend source during
this build): `UnlockTokenRedeemView` on the backend relies on JWT + nonce-
replay protection only, not `verify_device_signature`. This is a reasonable
defense-in-depth improvement to consider for a future iteration, not a bug
blocking this phase's functionality — carried into
`docs/03-REQUIREMENTS-AUDIT.md`.

### 8. `AuthTokenStore` uses unencrypted DataStore
Flagged in that file's own doc comment: JWT tokens are stored in a plain
(app-sandboxed, but not hardware-encrypted) preferences file. Migrating to
`EncryptedSharedPreferences` or an encrypted DataStore variant is a real
hardening step for a production release, not done in this phase.

## What is explicitly NOT built in this phase (see architecture doc §0.2)

- The full onboarding UI (goals -> apps -> limits -> weekly-lock decision) —
  `MainActivity`'s `OnboardingPermissionsScreen` covers only the
  permission-granting steps, functionally, not the full flow's UI/UX.
- The Secure Unlock request flow's actual network wiring from
  `BlockedAppOverlayActivity` — the buttons exist and are documented as
  visibly unwired rather than faked; wiring to the already-built
  `KernoApi.requestUnlock`/`redeemUnlockToken` is a mechanical next step.
- Website-time analytics — `DomainFilterVpnService` makes block/allow
  decisions but does not measure visit duration; see `ActivitySyncWorker`'s
  doc comment for why and what it would take.
- iOS entirely (architecture doc §3.2 — documented, not built, this phase).
