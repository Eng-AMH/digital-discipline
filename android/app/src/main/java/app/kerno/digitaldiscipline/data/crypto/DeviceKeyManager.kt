package app.kerno.digitaldiscipline.data.crypto

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.PublicKey
import java.security.Signature
import android.util.Base64
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Device identity per architecture doc §5.2: "لا نخزن الـ Secret الخام في
 * قاعدة البيانات" — the private key is generated INSIDE the Android Keystore
 * (hardware-backed on devices with a StrongBox or TEE, software-backed as a
 * fallback on older/cheaper devices) and is NEVER extractable as raw bytes,
 * not even by this app's own code. Only `getPublicKeyBase64()` ever leaves
 * this class boundary to be sent to the server.
 *
 * IMPLEMENTATION NOTE ON Ed25519 + Keystore: Android's KeyStore provider
 * historically only guaranteed EC (P-256) and RSA key support; Ed25519 support
 * via AndroidKeyStore was added more broadly starting around Android 13/14
 * (API 33+) on devices with compatible hardware/StrongBox implementations.
 * Since this app's minSdk is 26 (architecture doc's own choice, for
 * AccessibilityService/WorkManager reliability reasons unrelated to crypto),
 * there is a real compatibility gap: some devices this app supports may not
 * have hardware Ed25519 Keystore support. This class handles that explicitly
 * via `isHardwareEd25519Available()` and a software-backed Tink fallback,
 * documented in the fallback path below — rather than assuming Keystore
 * Ed25519 works everywhere and silently crashing on devices where it doesn't.
 */
@Singleton
class DeviceKeyManager @Inject constructor() {

    companion object {
        private const val KEYSTORE_PROVIDER = "AndroidKeyStore"
        private const val KEY_ALIAS = "kerno_device_identity_ed25519"
    }

    private val keyStore: KeyStore = KeyStore.getInstance(KEYSTORE_PROVIDER).apply { load(null) }

    /**
     * Returns true if hardware-backed AndroidKeyStore Ed25519 generation is
     * supported on this device. Checked via a real generation attempt rather
     * than a static SDK-version check, since Ed25519 Keystore support depends
     * on the device's specific security hardware/HAL implementation, not
     * purely on the Android API level — a version check alone could produce
     * false positives on API 33+ devices with older/incomplete HAL support.
     */
    private fun isHardwareEd25519Available(): Boolean {
        return try {
            val testAlias = "kerno_ed25519_probe"
            val generator = KeyPairGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_EC, KEYSTORE_PROVIDER
            )
            // NOTE: as of this writing, AndroidKeyStore's KeyProperties does not
            // expose a KEY_ALGORITHM_ED25519 constant in all supported API
            // levels uniformly — this probes via the algorithm string directly
            // where needed. Real device testing (see README.md checklist) is
            // required to confirm this probe behaves correctly across the
            // actual device fleet this app targets; documented here as an
            // assumption to validate, not a settled fact.
            generator.initialize(
                KeyGenParameterSpec.Builder(testAlias, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
                    .setAlgorithmParameterSpec(java.security.spec.ECGenParameterSpec("ed25519"))
                    .build()
            )
            generator.generateKeyPair()
            keyStore.deleteEntry(testAlias)
            true
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Software-backed fallback signer, used ONLY when hardware Keystore
     * Ed25519 is unavailable (see isHardwareEd25519Available above). This
     * stores the private key encrypted at rest via Tink's Android Keystore
     * integration (AEAD-wrapped, not plaintext-on-disk) — meaningfully weaker
     * than true hardware-backed non-extractability, but still far better than
     * an unencrypted key file, and honestly documented as the fallback tier
     * it is rather than presented as equivalent security to the hardware path.
     */
    private var softwareFallbackSigner: SoftwareEd25519Signer? = null

    private val useHardwareBacking: Boolean by lazy { isHardwareEd25519Available() }

    /**
     * Idempotent — safe to call on every app start. Only generates a new
     * keypair if one doesn't already exist for this install.
     */
    fun ensureKeyPairExists() {
        if (useHardwareBacking) {
            if (!keyStore.containsAlias(KEY_ALIAS)) {
                val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, KEYSTORE_PROVIDER)
                generator.initialize(
                    KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
                        .setAlgorithmParameterSpec(java.security.spec.ECGenParameterSpec("ed25519"))
                        .build()
                )
                generator.generateKeyPair()
            }
        } else {
            softwareFallbackSigner = SoftwareEd25519Signer.getOrCreate()
        }
    }

    fun getPublicKeyBase64(): String {
        ensureKeyPairExists()
        val rawPublicKeyBytes: ByteArray = if (useHardwareBacking) {
            val cert = keyStore.getCertificate(KEY_ALIAS)
            extractRawEd25519PublicKeyBytes(cert.publicKey)
        } else {
            softwareFallbackSigner!!.publicKeyBytes()
        }
        return Base64.encodeToString(rawPublicKeyBytes, Base64.NO_WRAP)
    }

    /**
     * Signs [canonicalJsonBytes] — the caller MUST have already run the
     * payload through [CanonicalJson.encode] before calling this, since
     * signing arbitrary un-canonicalized JSON would produce a signature the
     * server's signature verification (which reconstructs canonical JSON on
     * its side) could never match.
     */
    fun signCanonicalPayload(canonicalJsonBytes: ByteArray): String {
        ensureKeyPairExists()
        val rawSignature: ByteArray = if (useHardwareBacking) {
            val privateKey = keyStore.getKey(KEY_ALIAS, null) as PrivateKey
            // UNVERIFIED ASSUMPTION, flagged rather than silently trusted:
            // Signature.getInstance("Ed25519") against a Keystore-generated
            // key created via ECGenParameterSpec("ed25519") is the API pattern
            // documented for Android's Ed25519 Keystore support, but I cannot
            // compile/run this in the current environment to confirm the
            // algorithm string and generation path are actually compatible on
            // real devices/API levels. If this throws
            // InvalidKeyException/NoSuchAlgorithmException during Android
            // Studio integration, the fix is likely a different algorithm
            // string ("EdDSA" is used in some JCA provider documentation) —
            // this is the third item on README.md's device-testing checklist.
            val signature = Signature.getInstance("Ed25519")
            signature.initSign(privateKey)
            signature.update(canonicalJsonBytes)
            signature.sign()
        } else {
            softwareFallbackSigner!!.sign(canonicalJsonBytes)
        }
        return Base64.encodeToString(rawSignature, Base64.NO_WRAP)
    }

    /**
     * Android Keystore certificates wrap the raw Ed25519 public key inside an
     * X.509 structure — the server expects the RAW 32-byte public key (matching
     * cryptography.hazmat's Ed25519PublicKey.public_bytes_raw() on the Python
     * side, per apps.policies.services.server_public_key_b64's own format).
     * This extracts those raw bytes from the X.509-wrapped key rather than
     * sending the full encoded certificate, which the server would not be able
     * to parse as an Ed25519PublicKey via public_bytes_raw's expected format.
     */
    private fun extractRawEd25519PublicKeyBytes(publicKey: PublicKey): ByteArray {
        // X.509 SubjectPublicKeyInfo for Ed25519 has a fixed 12-byte header
        // (per RFC 8410) preceding the raw 32-byte key — this offset is a
        // documented, stable part of the DER encoding for this specific key
        // type, not a heuristic.
        val encoded = publicKey.encoded
        return encoded.copyOfRange(encoded.size - 32, encoded.size)
    }
}
