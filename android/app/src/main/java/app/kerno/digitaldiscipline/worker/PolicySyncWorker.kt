package app.kerno.digitaldiscipline.worker

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import app.kerno.digitaldiscipline.data.crypto.PolicyBlobVerifier
import app.kerno.digitaldiscipline.data.local.AuthTokenStore
import app.kerno.digitaldiscipline.data.local.CachedAppLimit
import app.kerno.digitaldiscipline.data.local.CachedFocusSession
import app.kerno.digitaldiscipline.data.local.CachedPolicyEntity
import app.kerno.digitaldiscipline.data.local.CachedSchedule
import app.kerno.digitaldiscipline.data.local.CachedWebsiteLimit
import app.kerno.digitaldiscipline.data.local.PolicyCacheDao
import app.kerno.digitaldiscipline.data.remote.KernoApi
import app.kerno.digitaldiscipline.data.remote.model.SignedPolicyBlob
import app.kerno.digitaldiscipline.enforcement.BlockedDomainsRepository
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.time.Instant
import java.time.LocalTime

/**
 * Implements the sync half of architecture §5.4's offline-first design: fetch
 * the signed policy blob, VERIFY it via PolicyBlobVerifier (the actual
 * security checkpoint — see that class's doc comment), and only if valid,
 * write it to the Room cache PolicyEnforcementEngine reads from. An
 * invalid/unverifiable blob is discarded, NOT cached — the device continues
 * enforcing whatever it last successfully verified, which is the correct
 * fail-safe behavior (matching CachedPolicyEntity's grace-period design)
 * rather than either caching untrusted data or wiping the last-known-good
 * policy on a single verification hiccup.
 *
 * SCHEDULING: registered as periodic work (see KernoApplication) at the same
 * 6-hour cadence the backend uses for policy blob validity
 * (apps.policies.services.build_signed_policy_blob's default valid_hours=6),
 * PLUS triggered as one-off expedited work immediately after any user action
 * that changes policy while online (e.g. confirming a Weekly Plan) — the
 * periodic schedule is the fallback that guarantees eventual consistency even
 * if an immediate trigger is ever missed, not the only sync path.
 */
@HiltWorker
class PolicySyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val kernoApi: KernoApi,
    private val policyBlobVerifier: PolicyBlobVerifier,
    private val policyCacheDao: PolicyCacheDao,
    private val blockedDomainsRepository: BlockedDomainsRepository,
    private val authTokenStore: AuthTokenStore
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val deviceId = authTokenStore.getDeviceId() ?: return Result.failure()

        val response = try {
            kernoApi.getOfflinePolicyBlob(deviceId)
        } catch (e: Exception) {
            // Network failure — retry via WorkManager's normal backoff policy
            // rather than failure, since this is expected/recoverable
            // (architecture §5.4 explicitly designs for connectivity gaps).
            return Result.retry()
        }

        val blob = response.body()
        if (!response.isSuccessful || blob == null) return Result.retry()

        return when (val verification = policyBlobVerifier.verify(blob)) {
            is PolicyBlobVerifier.VerificationResult.Invalid -> {
                // Do NOT retry on a verification failure — a signature that's
                // invalid now will be invalid on immediate retry too (unlike
                // a network error), and retrying rapidly would just spam
                // failed verification attempts. Fail this work run; the next
                // PERIODIC run will naturally try again with a fresh blob.
                Result.failure()
            }
            is PolicyBlobVerifier.VerificationResult.Valid -> {
                cacheVerifiedPolicy(verification.blob)
                Result.success()
            }
        }
    }

    private suspend fun cacheVerifiedPolicy(blob: SignedPolicyBlob) {
        val payload = blob.payload

        val entity = CachedPolicyEntity(
            issuedAtEpochMillis = Instant.parse(normalizeIsoInstant(payload.issuedAt)).toEpochMilli(),
            validUntilEpochMillis = Instant.parse(normalizeIsoInstant(payload.validUntil)).toEpochMilli(),
            appLimits = payload.appLimits.map {
                CachedAppLimit(it.packageName, it.displayName, it.dailyMinutes)
            },
            websiteLimits = payload.websiteLimits.map {
                CachedWebsiteLimit(it.domain, it.category, it.dailyMinutes)
            },
            schedules = payload.schedules.map {
                CachedSchedule(
                    mode = it.mode,
                    // Backend sends "HH:MM:SS" (Django TimeField's default
                    // str() format, per apps.policies.services.build_signed_policy_blob's
                    // json.dumps(default=str) normalization). LocalTime.parse
                    // accepts "HH:MM:SS" directly as valid ISO-8601 local
                    // time — no substring/truncation needed. An earlier draft
                    // of this line applied an unnecessary substringBeforeLast
                    // manipulation that would have silently truncated seconds
                    // (e.g. "14:30:05" -> "14:30", losing the ":05"); caught
                    // during drafting and removed rather than shipped.
                    startTime = LocalTime.parse(it.startTime),
                    endTime = LocalTime.parse(it.endTime),
                    daysOfWeek = it.daysOfWeek,
                    blockedPackages = it.blockedPackages,
                    allowedPackages = it.allowedPackages
                )
            },
            activeFocusSession = payload.activeFocusSession?.let {
                CachedFocusSession(it.id, it.plannedMinutes, it.allowedPackages, it.blockedPackages)
            }
        )

        policyCacheDao.upsertPolicy(entity)
        blockedDomainsRepository.refreshFromCache()
    }

    /**
     * VERIFIED against the actual backend source during this build session
     * (apps.policies.services.build_signed_policy_blob, lines defining
     * "issued_at": now.isoformat() and "valid_until": valid_until.isoformat())
     * — Django's isoformat() is called EXPLICITLY on these two fields before
     * they enter the payload dict, so json.dumps's default=str fallback never
     * actually applies to them (an initial isolated test of mine incorrectly
     * assumed default=str's bare-datetime str() behavior applied here, which
     * would have produced a space-separated, non-Instant.parse-compatible
     * format — re-checked against the real function and corrected). The
     * CONFIRMED real format is "2026-08-24T09:44:01.577091+00:00" — a
     * T-separated ISO-8601 string with microseconds and a "+00:00" UTC
     * offset. java.time.Instant.parse requires a "Z" suffix or a
     * numeric-offset form it recognizes; this normalizes "+00:00" to "Z"
     * defensively, since confirming Instant.parse's exact acceptance
     * behavior for the "+00:00" form specifically would require running
     * Kotlin on a JVM, which isn't available in this environment.
     */
    private fun normalizeIsoInstant(raw: String): String =
        if (raw.endsWith("+00:00")) raw.removeSuffix("+00:00") + "Z" else raw
}
