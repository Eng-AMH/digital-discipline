package app.kerno.digitaldiscipline.data.remote

import app.kerno.digitaldiscipline.data.remote.model.SignedPolicyBlob
import app.kerno.digitaldiscipline.data.remote.model.UnlockTokenResponse
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

/**
 * Covers the subset of docs/01-REQUIREMENTS-AND-ARCHITECTURE.md §12 Core API
 * that the Android AGENT itself needs — device lifecycle, offline policy sync,
 * unlock redemption, activity batch upload. Account-management, social,
 * gamification-browsing, and monetization-browsing endpoints are consumed by
 * the future web client and are NOT duplicated here; this interface is scoped
 * to what the on-device enforcement agent actually calls, matching this
 * build's Android-focused scope for this phase.
 */
interface KernoApi {

    @POST("api/devices/register/")
    suspend fun registerDevice(@Body request: DeviceRegisterRequest): Response<DeviceResponse>

    @POST("api/devices/{deviceId}/heartbeat/")
    suspend fun sendHeartbeat(
        @Path("deviceId") deviceId: String,
        @Body request: HeartbeatRequest
    ): Response<DeviceResponse>

    @GET("api/policies/offline-blob/{deviceId}/")
    suspend fun getOfflinePolicyBlob(@Path("deviceId") deviceId: String): Response<SignedPolicyBlob>

    @POST("api/devices/{deviceId}/activity-sync/")
    suspend fun syncActivityBatch(
        @Path("deviceId") deviceId: String,
        @Body request: ActivityLogBatchRequest
    ): Response<ActivitySyncResponse>

    @POST("api/policies/unlock/request/")
    suspend fun requestUnlock(@Body request: UnlockRequestBody): Response<UnlockRequestResponse>

    @POST("api/policies/unlock/token/{tokenId}/redeem/")
    suspend fun redeemUnlockToken(
        @Path("tokenId") tokenId: String,
        @Body request: RedeemTokenRequest
    ): Response<UnlockTokenResponse>

    @GET("api/devices/server-public-key/")
    suspend fun getServerPublicKey(): Response<ServerPublicKeyResponse>
}

data class DeviceRegisterRequest(
    val platform: String = "ANDROID",
    val name: String,
    val model_name: String,
    val os_version: String,
    val app_version: String,
    val public_key: String
)

data class DeviceResponse(
    val id: String,
    val platform: String,
    val name: String,
    val is_active: Boolean,
    val is_healthy: Boolean
)

data class HeartbeatRequest(
    val accessibility_service_active: Boolean,
    val vpn_service_active: Boolean,
    val usage_access_granted: Boolean,
    // Populated by DeviceSigningInterceptor, not set at call site — see that
    // class's doc comment for why the interceptor, not this call site, owns
    // computing this field. Left as an empty default here purely so callers
    // can construct this data class without needing to know about signing.
    val signature: String = ""
)

data class ActivityLogEntry(
    val target_type: String,
    val target_identifier: String,
    val occurred_date: String,
    val minutes_used: Int,
    val session_started_at: String,
    val session_ended_at: String
)

data class ActivityLogBatchRequest(val entries: List<ActivityLogEntry>)
data class ActivitySyncResponse(val synced_count: Int)

data class UnlockRequestBody(
    val device: String,
    val package_name: String,
    val requested_minutes: Int,
    val reason_type: String,
    val reason_note: String = ""
)

data class UnlockRequestResponse(
    val id: String,
    val status: String
)

data class RedeemTokenRequest(val device: String)

data class ServerPublicKeyResponse(val server_public_key: String)
