package app.kerno.digitaldiscipline.data.local

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Insert
import java.time.LocalDate
import java.util.UUID

/**
 * One row per (package, session) — NOT pre-aggregated per day. Aggregation
 * happens at query time (getMinutesUsedToday) and at sync time (see
 * worker/ActivitySyncWorker.kt, which batches these into the shape
 * apps.devices.serializers.ActivityLogBatchSerializer expects). Storing raw
 * sessions rather than a running per-day counter means a sync failure or app
 * restart can never lose partial-day data or double-count — the source of
 * truth is always "the list of sessions that actually happened."
 */
@Entity(tableName = "usage_session")
data class UsageSessionEntity(
    @PrimaryKey val id: String = UUID.randomUUID().toString(),
    val packageName: String,
    val occurredDate: String, // ISO LocalDate string (YYYY-MM-DD), matching the
                               // backend's ActivityLog.occurred_date DateField format
    val minutesUsed: Int,
    val sessionStartedAtEpochMillis: Long,
    val sessionEndedAtEpochMillis: Long,
    val syncedToServer: Boolean = false
)

@Dao
interface UsageTrackingDao {

    @Insert
    suspend fun insertSession(session: UsageSessionEntity)

    @Query(
        "SELECT COALESCE(SUM(minutesUsed), 0) FROM usage_session " +
            "WHERE packageName = :packageName AND occurredDate = :date"
    )
    suspend fun getMinutesUsedTodayRaw(packageName: String, date: String): Int

    suspend fun getMinutesUsedToday(packageName: String, date: LocalDate): Int =
        getMinutesUsedTodayRaw(packageName, date.toString())

    @Query("SELECT * FROM usage_session WHERE syncedToServer = 0 ORDER BY sessionStartedAtEpochMillis ASC LIMIT :limit")
    suspend fun getUnsyncedSessions(limit: Int = 200): List<UsageSessionEntity>

    @Query("UPDATE usage_session SET syncedToServer = 1 WHERE id IN (:ids)")
    suspend fun markSynced(ids: List<String>)

    // §16 Advanced Analytics / §19 Focus Score need trailing-window queries too
    // (e.g. "minutes used per day for the last 7 days") — those are computed
    // SERVER-SIDE from the synced ActivityLog table (apps.gamification.scoring),
    // not duplicated here, since the server is the authoritative source for
    // anything spanning more than "today" (architecture principle: Device only
    // caches what it needs for real-time enforcement, not full history).
}
