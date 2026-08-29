package app.kerno.digitaldiscipline.data.remote

import app.kerno.digitaldiscipline.data.crypto.CanonicalJson
import app.kerno.digitaldiscipline.data.crypto.DeviceKeyManager
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okio.Buffer
import org.json.JSONObject
import javax.inject.Inject

/**
 * Implements architecture §5.2: "every subsequent sensitive device action...
 * is a request signed by the device's private key." Rather than have every
 * call site remember to sign, this OkHttp Interceptor signs automatically for
 * requests hitting endpoints that need it (see SIGNED_ENDPOINT_SUFFIXES
 * below) — a call site cannot forget the signature because the interceptor,
 * not the call site, is responsible for it.
 *
 * WHICH ENDPOINTS ARE SIGNED, and why not all of them: signing every request
 * (including plain reads like "list my app limits") would add unnecessary
 * latency for no security benefit — those endpoints are already protected by
 * the JWT bearer token. Signing is reserved for the specific device-identity-
 * critical actions the backend actually verifies a device signature for:
 * heartbeat (apps.devices.views.DeviceHeartbeatView, via
 * apps.devices.services.record_heartbeat -> verify_device_signature). This
 * list MUST stay in sync with which backend views actually call
 * verify_device_signature — signing a request the backend doesn't check would
 * be harmless-but-wasteful; NOT signing one the backend DOES check would
 * cause every such request to fail with the generic "invalid_signature"
 * response, so this list is a real cross-codebase contract, not a local
 * implementation detail, and should be checked against apps/devices/services.py
 * and apps/policies/services.py on the backend during any future endpoint changes.
 *
 * NOTE ON UNLOCK TOKEN REDEMPTION: apps.policies.views.UnlockTokenRedeemView
 * does NOT currently call verify_device_signature on the backend (it
 * authenticates purely via the JWT bearer token + device ownership check) —
 * so "/redeem/" is deliberately NOT in this list, even though one might
 * expect it to be signed given how security-sensitive token redemption is.
 * This is flagged here as a design decision to revisit, not an oversight:
 * the backend's UnlockToken redemption is already replay-protected via the
 * nonce+redeemed_at mechanism (apps.policies.services.redeem_unlock_token),
 * which is arguably sufficient on its own, but adding device-signature
 * verification there too would be a reasonable defense-in-depth improvement
 * for a future iteration — noted in docs/03-REQUIREMENTS-AUDIT.md rather than
 * silently assumed already covered.
 */
class DeviceSigningInterceptor @Inject constructor(
    private val deviceKeyManager: DeviceKeyManager
) : Interceptor {

    companion object {
        private val SIGNED_ENDPOINT_SUFFIXES = listOf(
            "/heartbeat/"
        )
    }

    override fun intercept(chain: Interceptor.Chain): Response {
        val originalRequest = chain.request()
        val path = originalRequest.url.encodedPath

        val needsSigning = SIGNED_ENDPOINT_SUFFIXES.any { path.endsWith(it) }
        val originalBody = originalRequest.body
        if (!needsSigning || originalBody == null) {
            return chain.proceed(originalRequest)
        }

        // Buffer the original body so it can be read without irreversibly
        // consuming OkHttp's request body stream (which normally supports
        // only a single write/read pass) — the original `originalRequest`
        // object must remain independently usable for OkHttp's own internal
        // retry/redirect handling even after we've read its body here.
        val buffer = Buffer()
        originalBody.writeTo(buffer)
        val bodyString = buffer.readUtf8()

        val bodyJson = try {
            JSONObject(bodyString)
        } catch (e: Exception) {
            // Body isn't a JSON object — shouldn't happen for the known
            // request shape of the signed endpoints above, but fail safe by
            // proceeding unsigned rather than throwing from inside an
            // interceptor, which would surface as a confusing crash far from
            // the actual call site that built this request.
            return chain.proceed(originalRequest)
        }

        val bodyMap = jsonObjectToMap(bodyJson)
        val canonicalBytes = CanonicalJson.encode(bodyMap).toByteArray(Charsets.UTF_8)
        val signature = deviceKeyManager.signCanonicalPayload(canonicalBytes)

        // Signature is added as a field WITHIN the JSON body (matching
        // apps.devices.serializers.HeartbeatSerializer's `signature` field
        // expectation on the backend), not as an HTTP header — this mirrors
        // the design already committed to server-side (architecture §5.3/§9);
        // the client matches it rather than introducing a second convention.
        bodyJson.put("signature", signature)

        val mediaType = "application/json; charset=utf-8".toMediaTypeOrNull()
        val newBody = bodyJson.toString().toRequestBody(mediaType)

        val signedRequest = originalRequest.newBuilder()
            .method(originalRequest.method, newBody)
            .build()

        return chain.proceed(signedRequest)
    }

    private fun jsonObjectToMap(obj: JSONObject): Map<String, Any?> {
        val result = LinkedHashMap<String, Any?>()
        obj.keys().forEach { key -> result[key] = obj.get(key) }
        return result
    }
}
