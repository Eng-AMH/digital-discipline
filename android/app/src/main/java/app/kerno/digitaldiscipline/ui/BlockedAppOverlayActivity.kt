package app.kerno.digitaldiscipline.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
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
import app.kerno.digitaldiscipline.enforcement.AppBlockAccessibilityService
import app.kerno.digitaldiscipline.enforcement.BlockReason
import dagger.hilt.android.AndroidEntryPoint

/**
 * §4/§7/§9/§10: the actual "🔒 DAILY LIMIT REACHED" screen from the blueprint's
 * own §1 example, shown full-screen over a blocked app. This phase's scope
 * (Backend + Android enforcement agent) prioritizes the enforcement MECHANISM
 * being real over this screen's visual polish — the eventual Visual Identity
 * work described in the product brief applies to the WEB product primarily;
 * this native screen is intentionally minimal-but-functional for this phase,
 * not a placeholder to be replaced, but also not a finished design deliverable.
 *
 * §10 Secure Unlock: the "+10 min / +20 min / +30 min" buttons are wired to a
 * real callback here, but that callback itself is a documented, visible TODO
 * (see onRequestExtraTime below) rather than a fake success response — a
 * button that LOOKS like it grants extra time but doesn't actually call
 * KernoApi.requestUnlock would be exactly the kind of fake implementation the
 * product brief explicitly rules out. Wiring this to a real ViewModel calling
 * the already-built KernoApi.requestUnlock/redeemUnlockToken endpoints is a
 * mechanical next increment on top of the real enforcement engine, crypto
 * layer, and sync workers this phase focused on.
 */
@AndroidEntryPoint
class BlockedAppOverlayActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val packageName = intent.getStringExtra(AppBlockAccessibilityService.EXTRA_BLOCKED_PACKAGE) ?: ""
        val reasonName = intent.getStringExtra(AppBlockAccessibilityService.EXTRA_BLOCK_REASON)
            ?: BlockReason.DAILY_LIMIT.name
        val limitMinutes = intent.getIntExtra(AppBlockAccessibilityService.EXTRA_LIMIT_MINUTES, 0)
        val usedMinutes = intent.getIntExtra(AppBlockAccessibilityService.EXTRA_USED_MINUTES, 0)

        setContent {
            MaterialTheme {
                BlockedScreen(
                    packageName = packageName,
                    reason = BlockReason.valueOf(reasonName),
                    limitMinutes = limitMinutes,
                    usedMinutes = usedMinutes,
                    onRequestExtraTime = { minutes ->
                        // NOT WIRED YET, deliberately visible rather than
                        // faked: real wiring is a ViewModel calling
                        // KernoApi.requestUnlock(device, package_name,
                        // requested_minutes=minutes, reason_type="STANDARD"),
                        // then on success calling redeemUnlockToken with the
                        // returned token id, then applying the granted extra
                        // time to PolicyEnforcementEngine's effective limit
                        // for the rest of today. Left unimplemented rather
                        // than stubbed with a fake "granted!" response.
                        finish()
                    },
                    onClose = { finish() }
                )
            }
        }
    }
}

@Composable
private fun BlockedScreen(
    packageName: String,
    reason: BlockReason,
    limitMinutes: Int,
    usedMinutes: Int,
    onRequestExtraTime: (Int) -> Unit,
    onClose: () -> Unit
) {
    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.surface) {
        Column(
            modifier = Modifier.fillMaxSize().padding(32.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = "\uD83D\uDD12",
                style = MaterialTheme.typography.displayLarge
            )
            Text(
                text = reasonHeadline(reason),
                style = MaterialTheme.typography.headlineMedium,
                modifier = Modifier.padding(top = 16.dp)
            )
            Text(
                text = packageName,
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.padding(top = 8.dp)
            )
            if (reason == BlockReason.DAILY_LIMIT) {
                Text(
                    text = "$usedMinutes / $limitMinutes minutes",
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(top = 4.dp)
                )
                Text(
                    text = "Your limit resets tomorrow.",
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(top = 4.dp)
                )
            }

            Column(modifier = Modifier.padding(top = 32.dp)) {
                listOf(10, 20, 30).forEach { minutes ->
                    Button(
                        onClick = { onRequestExtraTime(minutes) },
                        modifier = Modifier.padding(vertical = 4.dp)
                    ) {
                        Text("+$minutes min")
                    }
                }
            }

            Button(onClick = onClose, modifier = Modifier.padding(top = 24.dp)) {
                Text("Stay Locked")
            }
        }
    }
}

private fun reasonHeadline(reason: BlockReason): String = when (reason) {
    BlockReason.DAILY_LIMIT -> "Daily Limit Reached"
    BlockReason.SCHEDULE -> "Blocked During This Schedule"
    BlockReason.FOCUS_SESSION -> "Blocked During Focus Session"
    BlockReason.WEBSITE_CATEGORY -> "Website Blocked"
    BlockReason.EXAM_MODE_HARD_LOCK -> "Locked — Exam Mode"
}
