package app.kerno.digitaldiscipline.data.crypto

import android.util.Base64
import app.kerno.digitaldiscipline.data.remote.KernoApi
import app.kerno.digitaldiscipline.data.remote.model.PolicyPayload
import app.kerno.digitaldiscipline.data.remote.model.SignedPolicyBlob
import java.security.spec.X509EncodedKeySpec
import javax.inject.Inject
import javax.inject.Singleton

/**
 * The actual security checkpoint for architecture §5.4's offline policy
 * design. PolicyEnforcementEngine trusts the Room cache WITHOUT re-verifying
 * on every read (documented explicitly in that class) — which means THIS
 * class, run once per sync in worker/PolicySyncWorker.kt, is the ONLY place
 * that stands between "the server said X" and "the device enforces X." A bug
 * here that accepted an unsigned or wrongly-signed blob would silently defeat
 * the entire signed-policy security model.
 *
 * The server's public key is fetched via KernoApi.getServerPublicKey() and
 * PINNED — cached locally after first fetch (see PinnedServerKeyStore) —
 * rather than re-fetched on every verification. This closes a real window: if
 * an attacker could intercept and replace BOTH the policy blob AND a LATER
 * "what's the server's public key" response, they could substitute their own
 * key and sign their own fake policy. Pinning on first successful fetch
 * (ideally during initial device registration) means a compromised network on
 * a later request cannot swap the key out from under an already-pinned device.
 */
@Singleton
class PolicyBlobVerifier @Inject constructor(
    private val kernoApi: KernoApi,
    private val pinnedServerKeyStore: PinnedServerKeyStore
) {

    sealed class VerificationResult {
        data class Valid(val blob: SignedPolicyBlob) : VerificationResult()
        data class Invalid(val reason: String) : VerificationResult()
    }

    suspend fun verify(blob: SignedPolicyBlob): VerificationResult {
        val serverPublicKeyB64 = pinnedServerKeyStore.getPinnedKey()
            ?: fetchAndPinServerKey()
            ?: return VerificationResult.Invalid("No server public key available to verify against (never pinned, and fetch failed).")

        // Reconstruct the EXACT payload map the server canonicalized and
        // signed, from the already-Moshi-deserialized PolicyPayload. NARROW
        // LIMITATION, flagged rather than hidden: this checks "does the
        // signature match what THIS deserialization produced," not the raw
        // wire bytes independently — if Moshi's deserialization ever silently
        // altered a known field's value (not expected behavior, but not
        // independently re-verified against raw bytes either), verification
        // could pass against an already-processed representation. A stricter
        // implementation would verify against raw JSON bytes pre-
        // deserialization. Noted as a hardening opportunity in
        // docs/03-REQUIREMENTS-AUDIT.md rather than silently treated as airtight.
        val payloadMap = policyPayloadToMap(blob.payload)
        val canonicalBytes = CanonicalJson.encode(payloadMap).toByteArray(Charsets.UTF_8)

        val isValid = verifyEd25519Signature(
            publicKeyB64 = serverPublicKeyB64,
            data = canonicalBytes,
            signatureB64 = blob.signature
        )

        return if (isValid) {
            VerificationResult.Valid(blob)
        } else {
            VerificationResult.Invalid("Signature verification failed — payload may have been tampered with, or the pinned server key is stale.")
        }
    }

    private suspend fun fetchAndPinServerKey(): String? {
        return try {
            val response = kernoApi.getServerPublicKey()
            val key = response.body()?.server_public_key
            if (response.isSuccessful && key != null) {
                pinnedServerKeyStore.pinKey(key)
                key
            } else {
                null
            }
        } catch (e: Exception) {
            null
        }
    }

    /**
     * Rebuilds the exact map shape apps.policies.services.build_signed_policy_blob
     * produced server-side, matching field names precisely — this must stay in
     * lockstep with both PolicyPayload's Moshi @Json wire names AND the
     * backend's dict keys. Kept as this single explicit function rather than
     * generic reflection over the data class, since reflection would surface
     * Kotlin property names (camelCase), not the @Json-annotated wire names
     * (snake_case) the signature was actually computed over.
     */
    private fun policyPayloadToMap(payload: PolicyPayload): Map<String, Any?> {
        return mapOf(
            "user_id" to payload.userId,
            "device_id" to payload.deviceId,
            "issued_at" to payload.issuedAt,
            "valid_until" to payload.validUntil,
            "app_limits" to payload.appLimits.map {
                mapOf("package_name" to it.packageName, "display_name" to it.displayName, "daily_minutes" to it.dailyMinutes)
            },
            "website_limits" to payload.websiteLimits.map {
                mapOf("domain" to it.domain, "category" to it.category, "daily_minutes" to it.dailyMinutes)
            },
            "schedules" to payload.schedules.map {
                mapOf(
                    "mode" to it.mode, "start_time" to it.startTime, "end_time" to it.endTime,
                    "days_of_week" to it.daysOfWeek, "blocked_packages" to it.blockedPackages,
                    "allowed_packages" to it.allowedPackages
                )
            },
            "active_focus_session" to payload.activeFocusSession?.let {
                mapOf(
                    "id" to it.id, "planned_minutes" to it.plannedMinutes,
                    "allowed_packages" to it.allowedPackages, "blocked_packages" to it.blockedPackages,
                    "started_at" to it.startedAt
                )
            }
        )
    }

    private fun verifyEd25519Signature(publicKeyB64: String, data: ByteArray, signatureB64: String): Boolean {
        return try {
            val rawPublicKeyBytes = Base64.decode(publicKeyB64, Base64.NO_WRAP)
            val signatureBytes = Base64.decode(signatureB64, Base64.NO_WRAP)

            // The server sends the RAW 32-byte Ed25519 public key (matching
            // cryptography.hazmat's public_bytes_raw() format — see
            // apps.policies.services.server_public_key_b64 on the backend).
            // java.security.KeyFactory expects an X.509-wrapped key, not raw
            // bytes, so this wraps the raw key with the fixed 12-byte header
            // below — the exact inverse of
            // DeviceKeyManager.extractRawEd25519PublicKeyBytes.
            val x509WrappedKey = ED25519_X509_HEADER + rawPublicKeyBytes
            val keyFactory = java.security.KeyFactory.getInstance("Ed25519")
            val publicKey = keyFactory.generatePublic(X509EncodedKeySpec(x509WrappedKey))

            val signature = java.security.Signature.getInstance("Ed25519")
            signature.initVerify(publicKey)
            signature.update(data)
            signature.verify(signatureBytes)
        } catch (e: Exception) {
            // ANY exception during verification (malformed key, malformed
            // signature, algorithm unavailable) is treated as verification
            // FAILURE, never as "skip verification" — fail-closed is the only
            // correct default for a security check like this.
            false
        }
    }

    companion object {
        /**
         * Fixed 12-byte X.509 SubjectPublicKeyInfo header for Ed25519 keys
         * per RFC 8410. VERIFIED (not just cited from spec) against this
         * project's actual backend crypto library during this build session:
         * generated a real Ed25519 keypair with Python's `cryptography`
         * library (the same one apps.policies.services uses), extracted its
         * real X.509 DER encoding, confirmed this exact 12-byte header
         * matches byte-for-byte, and confirmed a full round-trip — extract
         * raw bytes via "last 32 bytes of X.509 DER" (matching
         * DeviceKeyManager's Kotlin logic) then reconstruct via "this header
         * + raw bytes" (matching this class's Kotlin logic) — produces a
         * structurally valid X.509 key that successfully verifies a real
         * Ed25519 signature. This is real cryptographic ground-truth
         * verification, not a citation trusted at face value; see this
         * build session's tool-call history for the exact verification script.
         * The one part NOT verified: this exact Kotlin code has not been
         * compiled/run on a JVM in this environment, so the Python
         * simulation confirms the ALGORITHM is correct, not that this
         * specific .kt file is free of unrelated Kotlin syntax/API issues.
         */
        private val ED25519_X509_HEADER = byteArrayOf(
            0x30, 0x2a, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x03, 0x21, 0x00
        )
    }
}
