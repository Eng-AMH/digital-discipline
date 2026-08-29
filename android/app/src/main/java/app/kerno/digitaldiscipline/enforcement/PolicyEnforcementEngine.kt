package app.kerno.digitaldiscipline.enforcement

import app.kerno.digitaldiscipline.data.local.PolicyCacheDao
import app.kerno.digitaldiscipline.data.local.UsageTrackingDao
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.LocalTime
import javax.inject.Inject
import javax.inject.Singleton

/**
 * The actual §4/§5/§7/§8/§9 policy resolution logic, running entirely offline
 * against the Room-cached signed policy blob (architecture §5.4) and locally-
 * tracked usage minutes. This is the Android-side equivalent of the backend's
 * apps.policies.services module — deliberately mirroring its resolution order
 * so behavior is consistent whether the device is online or offline:
 *
 *   1. Active FocusSession (§7) — if running, ONLY allowed_packages pass;
 *      everything else blocks with reason FOCUS_SESSION.
 *   2. Active Schedule (§8) — if the current time falls within an enabled
 *      Schedule's window for today, its blocked_packages block outright with
 *      reason SCHEDULE.
 *   3. AppLimit (§4) — if today's tracked usage for this package meets or
 *      exceeds daily_minutes, block with reason DAILY_LIMIT.
 *   4. WebsiteLimit is NOT evaluated here — website blocking is a SEPARATE
 *      mechanism (DomainFilterVpnService, DNS-level), since a foregrounded
 *      BROWSER package (e.g. Chrome) is not itself over/under any per-package
 *      limit; the domain being visited inside it is what §6 restricts, and
 *      VpnService is the only mechanism with visibility into that.
 *
 * This engine trusts the LOCALLY CACHED policy blob's signature was already
 * verified at sync time (see worker/PolicySyncWorker.kt) — it does not
 * re-verify the signature on every accessibility event, since that would be
 * wasteful (Ed25519 verification is fast, but not free, and this runs on
 * every foreground-app change, potentially dozens of times per minute).
 */
@Singleton
class PolicyEnforcementEngine @Inject constructor(
    private val policyCacheDao: PolicyCacheDao,
    private val usageTrackingDao: UsageTrackingDao
) {

    suspend fun evaluateForegroundApp(packageName: String): EnforcementDecision {
        val cachedPolicy = policyCacheDao.getCurrentPolicy() ?: return EnforcementDecision.Allow
        // If the cached policy blob's own valid_until has passed and no
        // refresh has succeeded (see PolicySyncWorker's retry/backoff),
        // architecture §5.4 intends fail-open at the ENFORCEMENT level for a
        // bounded grace window (a user should not be permanently locked out of
        // their entire phone because of a sync failure) — but this is
        // deliberately narrow and documented, not a blanket bypass: see
        // isWithinGracePeriod below.
        if (cachedPolicy.isExpired() && !cachedPolicy.isWithinGracePeriod()) {
            return EnforcementDecision.Allow
        }

        val activeFocusSession = cachedPolicy.activeFocusSession
        if (activeFocusSession != null) {
            return if (packageName in activeFocusSession.allowedPackages) {
                EnforcementDecision.Allow
            } else {
                EnforcementDecision.Block(
                    reason = BlockReason.FOCUS_SESSION,
                    limitMinutes = activeFocusSession.plannedMinutes,
                    usedMinutes = 0
                )
            }
        }

        val now = LocalTime.now()
        val today = DayOfWeek.now().value - 1 // backend uses 0=Monday..6=Sunday; java.time DayOfWeek is 1=Monday..7=Sunday
        val activeSchedule = cachedPolicy.schedules.firstOrNull { schedule ->
            schedule.isEnabled &&
                today in schedule.daysOfWeek &&
                isTimeWithinWindow(now, schedule.startTime, schedule.endTime)
        }
        if (activeSchedule != null && packageName in activeSchedule.blockedPackages) {
            return EnforcementDecision.Block(
                reason = BlockReason.SCHEDULE,
                limitMinutes = 0,
                usedMinutes = 0
            )
        }

        val appLimit = cachedPolicy.appLimits.firstOrNull { it.packageName == packageName }
        if (appLimit != null) {
            val usedToday = usageTrackingDao.getMinutesUsedToday(packageName, LocalDate.now())
            if (usedToday >= appLimit.dailyMinutes) {
                return EnforcementDecision.Block(
                    reason = BlockReason.DAILY_LIMIT,
                    limitMinutes = appLimit.dailyMinutes,
                    usedMinutes = usedToday
                )
            }
        }

        return EnforcementDecision.Allow
    }

    private fun isTimeWithinWindow(now: LocalTime, start: LocalTime, end: LocalTime): Boolean {
        // Handles overnight windows correctly (e.g. Sleep Mode 23:00 -> 07:00,
        // per §5's own example) where start > end means the window wraps past
        // midnight — a naive `now in start..end` check would incorrectly treat
        // this as an always-false / zero-length window.
        return if (start <= end) {
            now in start..end
        } else {
            now >= start || now <= end
        }
    }
}

sealed class EnforcementDecision {
    object Allow : EnforcementDecision()
    data class Block(
        val reason: BlockReason,
        val limitMinutes: Int,
        val usedMinutes: Int
    ) : EnforcementDecision()
}

enum class BlockReason {
    DAILY_LIMIT, SCHEDULE, FOCUS_SESSION, WEBSITE_CATEGORY, EXAM_MODE_HARD_LOCK
}
