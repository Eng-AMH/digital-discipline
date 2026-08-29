package app.kerno.digitaldiscipline.enforcement

import android.app.admin.DeviceAdminReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * §9 Anti-Tamper ceiling case — see AndroidManifest.xml's comment on this
 * receiver's registration and res/xml/device_admin_policy.xml's comment on
 * why <uses-policies> is correctly empty. The bounded, honest capability this
 * class provides: while device admin is active, Android requires an extra
 * confirmation step before this app can be uninstalled via the normal Settings
 * > Apps flow. It does NOT and cannot prevent:
 *   - The user disabling device admin itself (Settings > Security > Device
 *     Admin Apps always allows this — Android guarantees it)
 *   - The user disabling the AccessibilityService or VPN independently
 *   - ADB-based uninstallation (adb uninstall bypasses the Settings-UI
 *     confirmation this receiver adds)
 * This class exists to warn/log on the deactivation attempt, not to block it.
 */
class DeviceAdminReceiverImpl : DeviceAdminReceiver() {

    override fun onEnabled(context: Context, intent: Intent) {
        super.onEnabled(context, intent)
        Log.i(TAG, "Device admin enabled.")
    }

    /**
     * Called when the user is ABOUT TO disable device admin, before it
     * actually happens. Returning a non-null String shows it as a warning
     * message in the system confirmation dialog — this is the full extent of
     * this app's influence over that flow; the user can still proceed past
     * this warning at will, per the class doc comment above.
     */
    override fun onDisableRequested(context: Context, intent: Intent): CharSequence {
        return "Disabling this will remove the extra confirmation step before Kerno can be uninstalled. " +
            "Your usage limits will continue to be enforced by the Accessibility Service and VPN filter " +
            "independently of this setting."
    }

    override fun onDisabled(context: Context, intent: Intent) {
        super.onDisabled(context, intent)
        Log.w(TAG, "Device admin disabled by user.")
        // FOLLOW-UP NOTE, not silently incomplete: reporting this event via
        // DeviceHealthReporter (similar to how AppBlockAccessibilityService
        // reports its own lifecycle) is not wired in this pass.
        // DeviceAdminReceiver instances are constructed directly by the
        // Android framework (via the manifest <receiver> registration), not
        // by Hilt, so getting a properly-injected DeviceHealthReporter here
        // requires Hilt's EntryPointAccessors pattern rather than the
        // @AndroidEntryPoint annotation used elsewhere in this codebase
        // (@AndroidEntryPoint doesn't apply to BroadcastReceiver in the same
        // way). Scoped out of this pass deliberately, documented here rather
        // than left as a silent gap.
    }

    companion object {
        private const val TAG = "DeviceAdminReceiver"
    }
}
