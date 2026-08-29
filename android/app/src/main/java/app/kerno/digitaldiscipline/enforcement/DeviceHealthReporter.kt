package app.kerno.digitaldiscipline.enforcement

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Aggregates the three booleans §9's Device Health payload needs
 * (accessibility_service_active, vpn_service_active, usage_access_granted)
 * from wherever they're actually observed — AppBlockAccessibilityService's
 * lifecycle callbacks, DomainFilterVpnService's lifecycle callbacks, and a
 * direct UsageStatsManager permission check respectively — into one place
 * worker/HeartbeatWorker.kt reads from before signing and sending a heartbeat.
 *
 * Deliberately in-memory (StateFlow) rather than persisted to Room/DataStore:
 * these booleans reflect CURRENT process state (is the service running RIGHT
 * NOW), and a value read from persistent storage after a process restart
 * would be stale until the relevant service's onServiceConnected/onCreate
 * actually re-fires — which happens quickly in practice, but persisting a
 * potentially-stale "was active" value would risk reporting a false positive
 * to the heartbeat in that narrow window, which is worse than the heartbeat
 * simply reflecting "unknown/false until proven active" on fresh process start.
 */
@Singleton
class DeviceHealthReporter @Inject constructor() {

    private val _accessibilityServiceActive = MutableStateFlow(false)
    val accessibilityServiceActive: StateFlow<Boolean> = _accessibilityServiceActive.asStateFlow()

    private val _vpnServiceActive = MutableStateFlow(false)
    val vpnServiceActive: StateFlow<Boolean> = _vpnServiceActive.asStateFlow()

    fun setAccessibilityServiceActive(active: Boolean) {
        _accessibilityServiceActive.value = active
    }

    fun setVpnServiceActive(active: Boolean) {
        _vpnServiceActive.value = active
    }

    fun currentSnapshot(usageAccessGranted: Boolean) = DeviceHealthSnapshot(
        accessibilityServiceActive = _accessibilityServiceActive.value,
        vpnServiceActive = _vpnServiceActive.value,
        usageAccessGranted = usageAccessGranted
    )
}

data class DeviceHealthSnapshot(
    val accessibilityServiceActive: Boolean,
    val vpnServiceActive: Boolean,
    val usageAccessGranted: Boolean
)
