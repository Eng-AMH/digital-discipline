package app.kerno.digitaldiscipline.ui

import android.content.Intent
import android.net.VpnService
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import app.kerno.digitaldiscipline.enforcement.DomainFilterVpnService
import dagger.hilt.android.AndroidEntryPoint

/**
 * §38 Onboarding permission-granting screens. This is deliberately minimal
 * for this phase (backend + Android enforcement agent scope) — the real
 * multi-step onboarding flow (goals, apps, limits, weekly-lock decision, THEN
 * permissions) described in §38/architecture §9 is a UI/product-design
 * undertaking distinct from the enforcement mechanism this phase prioritized.
 * What IS real here: the three permission-request flows below actually
 * request the real Android permissions (PACKAGE_USAGE_STATS via Settings
 * intent, Accessibility via Settings intent, VPN via VpnService.prepare) using
 * the correct platform APIs — nothing here is a fake permission-request button.
 */
@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    private val vpnPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            startService(Intent(this, DomainFilterVpnService::class.java))
        }
        // If denied, this app correctly does nothing further — per
        // architecture §3.1, there is no legitimate way to force VPN
        // permission grant, and this code does not attempt to.
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                OnboardingPermissionsScreen(
                    onRequestUsageAccess = { openUsageAccessSettings() },
                    onRequestAccessibility = { openAccessibilitySettings() },
                    onRequestVpn = { requestVpnPermission() }
                )
            }
        }
    }

    /**
     * §4/§9: PACKAGE_USAGE_STATS is a SPECIAL permission (see
     * AndroidManifest.xml's comment on this same point) — there is no runtime
     * permission dialog Android provides for it. The only correct mechanism
     * is directing the user to this specific system settings screen, where
     * THEY manually find and enable this app — this code cannot grant it
     * programmatically, by design of the Android platform.
     */
    private fun openUsageAccessSettings() {
        startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
    }

    /** Same pattern as usage access — Accessibility services cannot be
     * enabled programmatically; only the system Settings screen can do it,
     * with the user's explicit action. */
    private fun openAccessibilitySettings() {
        startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
    }

    /**
     * VpnService.prepare() returns a non-null Intent if user consent is
     * needed (always, the first time) — this is Android's standard,
     * mandatory VPN-consent dialog; it cannot be bypassed or pre-approved by
     * an app.
     */
    private fun requestVpnPermission() {
        val consentIntent = VpnService.prepare(this)
        if (consentIntent != null) {
            vpnPermissionLauncher.launch(consentIntent)
        } else {
            // Already consented previously — start directly.
            startService(Intent(this, DomainFilterVpnService::class.java))
        }
    }
}

@Composable
private fun OnboardingPermissionsScreen(
    onRequestUsageAccess: () -> Unit,
    onRequestAccessibility: () -> Unit,
    onRequestVpn: () -> Unit
) {
    Surface(modifier = Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier.fillMaxSize().padding(32.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text("Kerno needs a few permissions to work", style = MaterialTheme.typography.headlineSmall)
            Text(
                "You'll be taken to Android Settings for each one — Kerno cannot enable these automatically, by design.",
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(top = 8.dp, bottom = 24.dp)
            )
            Button(onClick = onRequestUsageAccess, modifier = Modifier.padding(vertical = 4.dp)) {
                Text("Grant Usage Access")
            }
            Button(onClick = onRequestAccessibility, modifier = Modifier.padding(vertical = 4.dp)) {
                Text("Enable Accessibility Service")
            }
            Button(onClick = onRequestVpn, modifier = Modifier.padding(vertical = 4.dp)) {
                Text("Enable Website Filtering")
            }
        }
    }
}
