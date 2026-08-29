package app.kerno.digitaldiscipline.data.local

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.first
import javax.inject.Inject
import javax.inject.Singleton

private val Context.authDataStore by preferencesDataStore(name = "kerno_auth_tokens")

/**
 * JWT access/refresh token storage. Matches the "DataStore for small key-value
 * config" split decided in app/build.gradle's dependency comments — the
 * policy cache itself is Room (data/local/PolicyCache.kt), this is for the
 * handful of scalar auth values where Room would be unnecessary overhead.
 *
 * SECURITY NOTE, honestly flagged: Preferences DataStore stores values in a
 * plain (unencrypted) file under the app's private data directory. This is
 * the standard Android sandboxing protection (another app cannot read this
 * file without root/a security bypass), but it is NOT hardware-encrypted the
 * way the Ed25519 private key in DeviceKeyManager is. For a production
 * release, migrating this to androidx.security's EncryptedSharedPreferences
 * or an encrypted DataStore variant would be a meaningful hardening step —
 * noted here as a real gap for docs/03-REQUIREMENTS-AUDIT.md rather than
 * silently treated as already secure-enough.
 */
@Singleton
class AuthTokenStore @Inject constructor(
    @ApplicationContext private val context: Context
) {
    companion object {
        private val ACCESS_TOKEN_KEY = stringPreferencesKey("access_token")
        private val REFRESH_TOKEN_KEY = stringPreferencesKey("refresh_token")
        private val DEVICE_ID_KEY = stringPreferencesKey("device_id")
    }

    suspend fun getAccessToken(): String? =
        context.authDataStore.data.first()[ACCESS_TOKEN_KEY]

    suspend fun getRefreshToken(): String? =
        context.authDataStore.data.first()[REFRESH_TOKEN_KEY]

    suspend fun getDeviceId(): String? =
        context.authDataStore.data.first()[DEVICE_ID_KEY]

    suspend fun saveTokens(accessToken: String, refreshToken: String) {
        context.authDataStore.edit { prefs ->
            prefs[ACCESS_TOKEN_KEY] = accessToken
            prefs[REFRESH_TOKEN_KEY] = refreshToken
        }
    }

    suspend fun saveDeviceId(deviceId: String) {
        context.authDataStore.edit { prefs -> prefs[DEVICE_ID_KEY] = deviceId }
    }

    suspend fun clear() {
        context.authDataStore.edit { it.clear() }
    }
}
