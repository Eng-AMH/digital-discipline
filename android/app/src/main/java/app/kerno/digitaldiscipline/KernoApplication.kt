package app.kerno.digitaldiscipline

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Application
import android.os.Build
import androidx.hilt.work.HiltWorkerFactory
import androidx.work.Configuration
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import app.kerno.digitaldiscipline.data.crypto.SoftwareEd25519Signer
import app.kerno.digitaldiscipline.worker.ActivitySyncWorker
import app.kerno.digitaldiscipline.worker.HeartbeatWorker
import app.kerno.digitaldiscipline.worker.PolicySyncWorker
import dagger.hilt.android.HiltAndroidApp
import java.util.concurrent.TimeUnit
import javax.inject.Inject

@HiltAndroidApp
class KernoApplication : Application(), Configuration.Provider {

    @Inject
    lateinit var workerFactory: HiltWorkerFactory

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder()
            .setWorkerFactory(workerFactory)
            .build()

    override fun onCreate() {
        super.onCreate()

        // Required before any DeviceKeyManager operation on devices without
        // hardware Ed25519 Keystore support — see SoftwareEd25519Signer's doc
        // comment for why this needs a Context and is initialized statically.
        SoftwareEd25519Signer.initialize(this)

        createNotificationChannels()
        schedulePeriodicWork()
    }

    /** §41 Notifications need a channel on Android 8.0+. This app's own
     * minSdk is 26, so the version check below is always true in practice —
     * kept explicit anyway for defensive correctness rather than silently
     * relying on minSdk never changing without this code being revisited. */
    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = getSystemService(NotificationManager::class.java)
            val enforcementChannel = NotificationChannel(
                CHANNEL_ENFORCEMENT,
                getString(R.string.notification_channel_enforcement_name),
                // limit-reached / protection-interrupted notifications are
                // high-importance — actionable, time-sensitive signals, not
                // passive updates.
                NotificationManager.IMPORTANCE_HIGH
            )
            val generalChannel = NotificationChannel(
                CHANNEL_GENERAL,
                getString(R.string.notification_channel_general_name),
                NotificationManager.IMPORTANCE_DEFAULT
            )
            manager.createNotificationChannel(enforcementChannel)
            manager.createNotificationChannel(generalChannel)
        }
    }

    /**
     * Registers the three periodic sync jobs. All three use
     * ExistingPeriodicWorkPolicy.KEEP rather than REPLACE — this matters
     * specifically because onCreate() runs on EVERY process start (not just
     * first install), and REPLACE would reset each job's schedule window on
     * every app launch, which in the worst case (frequent process restarts
     * under memory pressure) could prevent periodic work from ever actually
     * firing since it keeps getting rescheduled from "now."
     */
    private fun schedulePeriodicWork() {
        val workManager = WorkManager.getInstance(this)

        val networkConstraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()

        val policySyncRequest = PeriodicWorkRequestBuilder<PolicySyncWorker>(6, TimeUnit.HOURS)
            .setConstraints(networkConstraints)
            .build()
        workManager.enqueueUniquePeriodicWork(
            "policy_sync", ExistingPeriodicWorkPolicy.KEEP, policySyncRequest
        )

        val heartbeatRequest = PeriodicWorkRequestBuilder<HeartbeatWorker>(15, TimeUnit.MINUTES)
            .setConstraints(networkConstraints)
            .build()
        workManager.enqueueUniquePeriodicWork(
            "heartbeat", ExistingPeriodicWorkPolicy.KEEP, heartbeatRequest
        )

        val activitySyncRequest = PeriodicWorkRequestBuilder<ActivitySyncWorker>(1, TimeUnit.HOURS)
            .setConstraints(networkConstraints)
            .build()
        workManager.enqueueUniquePeriodicWork(
            "activity_sync", ExistingPeriodicWorkPolicy.KEEP, activitySyncRequest
        )
    }

    companion object {
        const val CHANNEL_ENFORCEMENT = "kerno_enforcement"
        const val CHANNEL_GENERAL = "kerno_general"
    }
}
