package app.kerno.digitaldiscipline.worker

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import app.kerno.digitaldiscipline.data.local.AuthTokenStore
import app.kerno.digitaldiscipline.data.local.UsageTrackingDao
import app.kerno.digitaldiscipline.data.remote.ActivityLogBatchRequest
import app.kerno.digitaldiscipline.data.remote.ActivityLogEntry
import app.kerno.digitaldiscipline.data.remote.KernoApi
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.time.Instant
import java.time.ZoneOffset

/**
 * Uploads locally-tracked UsageSessionEntity rows (see
 * data/local/UsageTrackingDao.kt) to the backend's ActivityLog in batches —
 * this is what makes §16 Advanced Analytics, §19 Focus Score, and §17 AI
 * Coach possible server-side, since all of those read from ActivityLog, not
 * from anything device-local.
 *
 * SCOPE GAP, flagged rather than silently assumed complete: this worker only
 * syncs APP usage (target_type="APP"). Website-domain visit TIME is not
 * tracked anywhere in this build — DomainFilterVpnService (verified by
 * re-reading that file) only makes a block/allow decision per DNS query, it
 * does not measure or record how long a domain was subsequently visited.
 * This means §16's website-specific analytics (as opposed to app-specific
 * analytics) have no data source in this build. Building that would require
 * either (a) VPN-level traffic-volume/duration heuristics per domain, which
 * is a meaningfully harder and more invasive undertaking than DNS-level
 * blocking, or (b) an AccessibilityService-based approach similar to app
 * tracking but for in-browser URL bars, which has its own reliability
 * caveats across different browser apps. Neither is implemented here —
 * carried forward explicitly into docs/03-REQUIREMENTS-AUDIT.md.
 */
@HiltWorker
class ActivitySyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val kernoApi: KernoApi,
    private val usageTrackingDao: UsageTrackingDao,
    private val authTokenStore: AuthTokenStore
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val deviceId = authTokenStore.getDeviceId() ?: return Result.failure()

        val unsynced = usageTrackingDao.getUnsyncedSessions()
        if (unsynced.isEmpty()) return Result.success()

        val entries = unsynced.map { session ->
            ActivityLogEntry(
                target_type = "APP",
                target_identifier = session.packageName,
                occurred_date = session.occurredDate,
                minutes_used = session.minutesUsed,
                session_started_at = Instant.ofEpochMilli(session.sessionStartedAtEpochMillis).atOffset(ZoneOffset.UTC).toString(),
                session_ended_at = Instant.ofEpochMilli(session.sessionEndedAtEpochMillis).atOffset(ZoneOffset.UTC).toString()
            )
        }

        return try {
            val response = kernoApi.syncActivityBatch(deviceId, ActivityLogBatchRequest(entries))
            if (response.isSuccessful) {
                usageTrackingDao.markSynced(unsynced.map { it.id })
                Result.success()
            } else {
                Result.retry()
            }
        } catch (e: Exception) {
            Result.retry()
        }
    }
}
