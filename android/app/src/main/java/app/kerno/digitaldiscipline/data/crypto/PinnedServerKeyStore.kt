package app.kerno.digitaldiscipline.data.crypto

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.first
import javax.inject.Inject
import javax.inject.Singleton

private val Context.serverKeyDataStore by preferencesDataStore(name = "kerno_pinned_server_key")

/**
 * See PolicyBlobVerifier's doc comment for WHY pinning matters. This class is
 * intentionally just persistent storage — it has no verification logic of its
 * own, so the security property ("once pinned, only explicit user/support
 * action can change it") lives entirely in the fact that nothing in this
 * codebase calls pinKey() except PolicyBlobVerifier.fetchAndPinServerKey(),
 * which itself only runs when getPinnedKey() returns null (i.e. first-ever
 * fetch). There is deliberately no "updateKey" or "rotateKey" method exposed
 * here — key rotation, if ever needed, is a deliberate out-of-band operation
 * (e.g. requiring the user to re-register their device), not a routine one.
 */
@Singleton
class PinnedServerKeyStore @Inject constructor(
    @ApplicationContext private val context: Context
) {
    companion object {
        private val PINNED_KEY = stringPreferencesKey("pinned_server_public_key")
    }

    suspend fun getPinnedKey(): String? =
        context.serverKeyDataStore.data.first()[PINNED_KEY]

    suspend fun pinKey(publicKeyB64: String) {
        context.serverKeyDataStore.edit { prefs -> prefs[PINNED_KEY] = publicKeyB64 }
    }
}
