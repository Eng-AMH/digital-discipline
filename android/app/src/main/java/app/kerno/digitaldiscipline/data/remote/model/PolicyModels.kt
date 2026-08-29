package app.kerno.digitaldiscipline.data.remote.model

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

/**
 * These data classes mirror the EXACT JSON shape produced by
 * apps.policies.services.build_signed_policy_blob() on the backend
 * (docs/01-REQUIREMENTS-AND-ARCHITECTURE.md §5.4). Field names, nullability, and
 * key ordering-independence (Moshi serializes by field name, matching the
 * server's canonical JSON which is also built from a Python dict with the same
 * keys) must match exactly, because the signature verification in
 * [app.kerno.digitaldiscipline.data.crypto.PolicyBlobVerifier] reconstructs the
 * canonical JSON from THESE classes and compares it against a signature the
 * server computed over ITS OWN canonical JSON. Any field name mismatch here
 * would silently break verification — not with an exception, but by producing
 * a canonical JSON string that doesn't match what the server signed, causing
 * every real policy sync to be rejected as "tampered."
 */

@JsonClass(generateAdapter = true)
data class SignedPolicyBlob(
    val payload: PolicyPayload,
    val signature: String
)

@JsonClass(generateAdapter = true)
data class PolicyPayload(
    @Json(name = "user_id") val userId: String,
    @Json(name = "device_id") val deviceId: String,
    @Json(name = "issued_at") val issuedAt: String,
    @Json(name = "valid_until") val validUntil: String,
    @Json(name = "app_limits") val appLimits: List<RemoteAppLimit>,
    @Json(name = "website_limits") val websiteLimits: List<RemoteWebsiteLimit>,
    val schedules: List<RemoteSchedule>,
    @Json(name = "active_focus_session") val activeFocusSession: RemoteFocusSession?
)

@JsonClass(generateAdapter = true)
data class RemoteAppLimit(
    @Json(name = "package_name") val packageName: String,
    @Json(name = "display_name") val displayName: String,
    @Json(name = "daily_minutes") val dailyMinutes: Int
)

@JsonClass(generateAdapter = true)
data class RemoteWebsiteLimit(
    val domain: String,
    val category: String,
    @Json(name = "daily_minutes") val dailyMinutes: Int?
)

@JsonClass(generateAdapter = true)
data class RemoteSchedule(
    val mode: String,
    // NOTE: the backend's Schedule.start_time/end_time are Django TimeFields,
    // serialized by json.dumps(default=str) into "HH:MM:SS" strings (see
    // apps.policies.services.build_signed_policy_blob's normalization step) —
    // represented here as String, not a parsed time type, specifically so the
    // canonical-JSON round-trip for signature verification reproduces the
    // exact same string the server signed, rather than a re-formatted one that
    // happens to represent the same time but differs byte-for-byte.
    @Json(name = "start_time") val startTime: String,
    @Json(name = "end_time") val endTime: String,
    @Json(name = "days_of_week") val daysOfWeek: List<Int>,
    @Json(name = "blocked_packages") val blockedPackages: List<String>,
    @Json(name = "allowed_packages") val allowedPackages: List<String>
)

@JsonClass(generateAdapter = true)
data class RemoteFocusSession(
    val id: String,
    @Json(name = "planned_minutes") val plannedMinutes: Int,
    @Json(name = "allowed_packages") val allowedPackages: List<String>,
    @Json(name = "blocked_packages") val blockedPackages: List<String>,
    @Json(name = "started_at") val startedAt: String
)

@JsonClass(generateAdapter = true)
data class UnlockTokenResponse(
    val id: String,
    @Json(name = "package_name") val packageName: String,
    @Json(name = "granted_minutes") val grantedMinutes: Int,
    val payload: UnlockTokenPayload,
    val signature: String,
    @Json(name = "issued_at") val issuedAt: String,
    @Json(name = "expires_at") val expiresAt: String
)

@JsonClass(generateAdapter = true)
data class UnlockTokenPayload(
    @Json(name = "device_id") val deviceId: String,
    @Json(name = "package_name") val packageName: String,
    @Json(name = "granted_minutes") val grantedMinutes: Int,
    val nonce: String,
    @Json(name = "issued_at") val issuedAt: String,
    @Json(name = "expires_at") val expiresAt: String
)
