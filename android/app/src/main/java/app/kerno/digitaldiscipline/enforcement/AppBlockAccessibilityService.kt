package app.kerno.digitaldiscipline.enforcement

import android.accessibilityservice.AccessibilityService
import android.content.Intent
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * The actual §4/§7/§9/§10 enforcement mechanism. Per architecture doc §3.1
 * point 2, this is a well-established, Play-compliant pattern (used by real
 * published apps in this category) as long as the declared purpose in
 * accessibility_service_config.xml's description genuinely matches what this
 * code does — which it must continue to, if this file is ever modified.
 *
 * WHAT THIS DOES: listens for TYPE_WINDOW_STATE_CHANGED events (fired when the
 * foreground app/activity changes), checks the newly-foregrounded package
 * against the locally-cached policy (via PolicyEnforcementEngine, which reads
 * from the Room-cached signed policy blob — see architecture §5.4), and if
 * that package is over its daily limit, blocked outright, or blocked by an
 * active Schedule/FocusSession, immediately launches BlockedAppOverlayActivity
 * on top of it.
 *
 * WHAT THIS DELIBERATELY DOES NOT DO: it does not read window CONTENT beyond
 * the package/class name needed to identify which app is foregrounded (even
 * though canRetrieveWindowContent=true is set in the service config, which is
 * required for reliable foreground-detection on some OEM skins — this
 * capability is not used to inspect on-screen text/content). It does not hide
 * itself from Android's Accessibility settings list. It does not attempt to
 * prevent the user from disabling it — per architecture §3.1 point 4, that is
 * a deliberate, correct limitation, not a missing feature.
 */
@AndroidEntryPoint
class AppBlockAccessibilityService : AccessibilityService() {

    @Inject
    lateinit var enforcementEngine: PolicyEnforcementEngine

    @Inject
    lateinit var deviceHealthReporter: DeviceHealthReporter

    private val serviceJob = SupervisorJob()
    private val serviceScope = CoroutineScope(Dispatchers.Default + serviceJob)

    override fun onServiceConnected() {
        super.onServiceConnected()
        Log.i(TAG, "AppBlockAccessibilityService connected.")
        // Reports accessibility_service_active=true on the next heartbeat —
        // see DeviceHealthReporter, which the WorkManager-scheduled heartbeat
        // job (see worker/HeartbeatWorker.kt) reads from before each server sync.
        deviceHealthReporter.setAccessibilityServiceActive(true)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null || event.eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) return

        val packageName = event.packageName?.toString() ?: return

        // Ignore our own app's packages — including the debug build's
        // applicationIdSuffix variant — so the block overlay itself, or the
        // main app UI, never triggers a recursive block-check against itself.
        if (packageName == applicationContext.packageName) return

        // Real enforcement decision happens off the main/binder thread — this
        // callback runs on the accessibility service's own thread, and Room
        // queries (inside enforcementEngine) must not block it, since a slow
        // accessibility callback can cause the system to consider the service
        // unresponsive.
        serviceScope.launch {
            val decision = enforcementEngine.evaluateForegroundApp(packageName)
            if (decision is EnforcementDecision.Block) {
                launchBlockOverlay(packageName, decision)
            }
        }
    }

    private fun launchBlockOverlay(packageName: String, decision: EnforcementDecision.Block) {
        val intent = Intent(this, app.kerno.digitaldiscipline.ui.BlockedAppOverlayActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            putExtra(EXTRA_BLOCKED_PACKAGE, packageName)
            putExtra(EXTRA_BLOCK_REASON, decision.reason.name)
            putExtra(EXTRA_LIMIT_MINUTES, decision.limitMinutes)
            putExtra(EXTRA_USED_MINUTES, decision.usedMinutes)
        }
        startActivity(intent)
    }

    override fun onInterrupt() {
        Log.w(TAG, "AppBlockAccessibilityService interrupted.")
    }

    override fun onDestroy() {
        super.onDestroy()
        // This callback firing means the user (or the system) disabled the
        // service. Per architecture §3.1 point 4, this is ALWAYS possible and
        // this code's only correct response is to DETECT and REPORT it — never
        // to attempt to restart itself in a way that fights the user's choice,
        // which would be exactly the kind of OS-protection circumvention the
        // product spec explicitly rules out.
        deviceHealthReporter.setAccessibilityServiceActive(false)
        serviceJob.cancel()
    }

    companion object {
        private const val TAG = "AppBlockA11yService"
        const val EXTRA_BLOCKED_PACKAGE = "extra_blocked_package"
        const val EXTRA_BLOCK_REASON = "extra_block_reason"
        const val EXTRA_LIMIT_MINUTES = "extra_limit_minutes"
        const val EXTRA_USED_MINUTES = "extra_used_minutes"
    }
}
