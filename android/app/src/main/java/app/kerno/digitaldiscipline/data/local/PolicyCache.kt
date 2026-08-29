package app.kerno.digitaldiscipline.data.local

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.TypeConverter
import androidx.room.TypeConverters
import androidx.room.Upsert
import com.squareup.moshi.Moshi
import com.squareup.moshi.adapter
import java.time.Instant
import java.time.LocalTime

/**
 * Single-row cache of the most recently synced, signature-verified policy blob
 * (architecture §5.4). There is deliberately only ever ONE row (id is fixed at
 * SINGLETON_ID) — a device has exactly one currently-effective policy snapshot
 * at a time; there is no reason to keep historical snapshots locally (the
 * server's ActivityLog/AuditLog already provide history where it matters).
 *
 * IMPORTANT: this entity is only ever written to by
 * worker/PolicySyncWorker.kt, and ONLY AFTER that worker has verified the
 * blob's Ed25519 signature via PolicyBlobVerifier. PolicyEnforcementEngine
 * trusts whatever is in this table WITHOUT re-verifying — the trust boundary
 * is "was this row written by the sync worker," which is enforced by there
 * being exactly one write path into this DAO, not by any check at read time.
 */
@Entity(tableName = "cached_policy")
@TypeConverters(PolicyTypeConverters::class)
data class CachedPolicyEntity(
    @PrimaryKey val id: Int = SINGLETON_ID,
    val issuedAtEpochMillis: Long,
    val validUntilEpochMillis: Long,
    val appLimits: List<CachedAppLimit>,
    val websiteLimits: List<CachedWebsiteLimit>,
    val schedules: List<CachedSchedule>,
    val activeFocusSession: CachedFocusSession?
) {
    companion object {
        const val SINGLETON_ID = 1

        /**
         * How long past `validUntil` the engine still enforces from this cache
         * before fail-open (see PolicyEnforcementEngine's grace-period comment).
         * Chosen as a genuine product/safety tradeoff, not an arbitrary number:
         * long enough to survive a typical multi-hour connectivity gap (e.g.
         * a flight, a rural dead zone) without the user's limits silently
         * evaporating, short enough that a permanently-offline device
         * (lost, stolen, or the account itself is compromised) doesn't enforce
         * a stale policy indefinitely with no way for the account owner to
         * update it remotely.
         */
        const val GRACE_PERIOD_HOURS = 24
    }

    fun isExpired(): Boolean = Instant.now().toEpochMilli() > validUntilEpochMillis

    fun isWithinGracePeriod(): Boolean {
        val graceMillis = GRACE_PERIOD_HOURS * 60 * 60 * 1000L
        return Instant.now().toEpochMilli() <= (validUntilEpochMillis + graceMillis)
    }
}

data class CachedAppLimit(val packageName: String, val displayName: String, val dailyMinutes: Int)

data class CachedWebsiteLimit(val domain: String, val category: String, val dailyMinutes: Int?)

data class CachedSchedule(
    val mode: String,
    val startTime: LocalTime,
    val endTime: LocalTime,
    val daysOfWeek: List<Int>,
    val blockedPackages: List<String>,
    val allowedPackages: List<String>,
    val isEnabled: Boolean = true
)

data class CachedFocusSession(
    val id: String,
    val plannedMinutes: Int,
    val allowedPackages: List<String>,
    val blockedPackages: List<String>
)

/**
 * Room requires TypeConverters for anything beyond primitives. Uses Moshi
 * (already a dependency for API responses) rather than a second JSON library,
 * so nested list/object fields serialize to a JSON string column.
 */
class PolicyTypeConverters {
    private val moshi = Moshi.Builder().build()

    @TypeConverter
    fun appLimitsToJson(value: List<CachedAppLimit>): String =
        moshi.adapter<List<CachedAppLimit>>().toJson(value)

    @TypeConverter
    fun appLimitsFromJson(value: String): List<CachedAppLimit> =
        moshi.adapter<List<CachedAppLimit>>().fromJson(value) ?: emptyList()

    @TypeConverter
    fun websiteLimitsToJson(value: List<CachedWebsiteLimit>): String =
        moshi.adapter<List<CachedWebsiteLimit>>().toJson(value)

    @TypeConverter
    fun websiteLimitsFromJson(value: String): List<CachedWebsiteLimit> =
        moshi.adapter<List<CachedWebsiteLimit>>().fromJson(value) ?: emptyList()

    @TypeConverter
    fun schedulesToJson(value: List<CachedSchedule>): String =
        moshi.adapter<List<CachedScheduleJson>>().toJson(value.map { it.toJsonModel() })

    @TypeConverter
    fun schedulesFromJson(value: String): List<CachedSchedule> =
        (moshi.adapter<List<CachedScheduleJson>>().fromJson(value) ?: emptyList()).map { it.toDomainModel() }

    @TypeConverter
    fun focusSessionToJson(value: CachedFocusSession?): String? =
        value?.let { moshi.adapter<CachedFocusSession>().toJson(it) }

    @TypeConverter
    fun focusSessionFromJson(value: String?): CachedFocusSession? =
        value?.let { moshi.adapter<CachedFocusSession>().fromJson(it) }
}

/**
 * Moshi cannot serialize java.time.LocalTime out of the box — this shadow
 * model swaps LocalTime for its ISO string form for the JSON round-trip only,
 * converted back to LocalTime for the actual CachedSchedule domain model that
 * the rest of the app (PolicyEnforcementEngine) works with.
 */
private data class CachedScheduleJson(
    val mode: String,
    val startTime: String,
    val endTime: String,
    val daysOfWeek: List<Int>,
    val blockedPackages: List<String>,
    val allowedPackages: List<String>,
    val isEnabled: Boolean
)

private fun CachedSchedule.toJsonModel() = CachedScheduleJson(
    mode, startTime.toString(), endTime.toString(), daysOfWeek, blockedPackages, allowedPackages, isEnabled
)

private fun CachedScheduleJson.toDomainModel() = CachedSchedule(
    mode, LocalTime.parse(startTime), LocalTime.parse(endTime), daysOfWeek, blockedPackages, allowedPackages, isEnabled
)

@Dao
interface PolicyCacheDao {
    @Query("SELECT * FROM cached_policy WHERE id = ${CachedPolicyEntity.SINGLETON_ID} LIMIT 1")
    suspend fun getCurrentPolicy(): CachedPolicyEntity?

    @Upsert
    suspend fun upsertPolicy(policy: CachedPolicyEntity)
}
