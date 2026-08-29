package app.kerno.digitaldiscipline.worker

import android.app.usage.UsageStatsManager
import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import app.kerno.digitaldiscipline.data.local.AuthTokenStore
import app.kerno.digitaldiscipline.data.remote.HeartbeatRequest
import app.kerno.digitaldiscipline.data.remote.KernoApi
import app.kerno.digitaldiscipline.enforcement.DeviceHealthReporter
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject

/**
 * §9 Device Health heartbeat. The actual signature computation happens
 * transparently in DeviceSigningInterceptor (registered for "/heartbeat/"
 * paths) — this worker only assembles the unsigned request body; it does not
 * call DeviceKeyManager directly, keeping the signing concern in exactly one
 * place per the interceptor's own design rationale.
 */
@HiltWorker
class HeartbeatWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val kernoApi: KernoApi,
    private val deviceHealthReporter: DeviceHealthReporter,
    private val authTokenStore: AuthTokenStore
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val deviceId = authTokenStore.getDeviceId() ?: return Result.failure()

        val usageAccessGranted = checkUsageStatsPermission()
        val snapshot = deviceHealthReporter.currentSnapshot(usageAccessGranted)

        val request = HeartbeatRequest(
            accessibility_service_active = snapshot.accessibilityServiceActive,
            vpn_service_active = snapshot.vpnServiceActive,
            usage_access_granted = snapshot.usageAccessGranted
            // signature field left at its default "" — DeviceSigningInterceptor
            // overwrites it before the request actually leaves the device; see
            // that class's doc comment.
        )

        return try {
            val response = kernoApi.sendHeartbeat(deviceId, request)
            if (response.isSuccessful) Result.success() else Result.retry()
        } catch (e: Exception) {
            Result.retry()
        }
    }

    /**
     * §4/§9: PACKAGE_USAGE_STATS is a special permission (see AndroidManifest.xml's
     * comment on this exact point) with no direct "isGranted" API — the
     * standard, documented way to check it is attempting a UsageStatsManager
     * query and observing whether it returns data, since a denied permission
     * causes queryUsageStats to return an empty/null result rather than throw.
     */
    private fun checkUsageStatsPermission(): Boolean {
        return try {
            val usageStatsManager = applicationContext.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
            val endTime = System.currentTimeMillis()
            val startTime = endTime - (60 * 1000) // last 1 minute is enough to probe access
            val stats = usageStatsManager.queryUsageStats(UsageStatsManager.INTERVAL_DAILY, startTime, endTime)
            !stats.isNullOrEmpty()
        } catch (e: Exception) {
            false
        }
    }
}
