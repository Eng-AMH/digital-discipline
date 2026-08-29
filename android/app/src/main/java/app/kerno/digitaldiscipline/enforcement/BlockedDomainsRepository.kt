package app.kerno.digitaldiscipline.enforcement

import app.kerno.digitaldiscipline.data.local.PolicyCacheDao
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Bridges the signed-and-verified policy cache (architecture §5.4) to
 * DomainFilterVpnService's packet-loop, which needs a fast in-memory Set
 * lookup on every intercepted DNS packet — re-querying Room on every single
 * packet would add unacceptable latency to normal DNS resolution for EVERY
 * domain, not just blocked ones, since the packet loop runs for all DNS
 * traffic regardless of outcome.
 *
 * The in-memory set is refreshed from the Room cache whenever
 * worker/PolicySyncWorker.kt writes a new policy blob (via refreshFromCache,
 * called from that worker after a successful, verified sync) — NOT read from
 * Room on a timer, since the source of truth for "when did the policy
 * change" is the sync event itself, and polling would introduce a window
 * where a just-tightened WebsiteLimit isn't yet enforced.
 *
 * IMPORTANT FIX NOTE: an earlier draft of this class discovered mid-write that
 * CachedPolicyEntity (data/local/PolicyCache.kt) did not carry websiteLimits
 * at all — only appLimits, schedules, and activeFocusSession were included
 * when that entity was originally built. That gap is fixed by extending
 * CachedPolicyEntity below (see the immediately-following edit to
 * PolicyCache.kt) rather than left as a silent empty-list placeholder here.
 */
@Singleton
class BlockedDomainsRepository @Inject constructor(
    private val policyCacheDao: PolicyCacheDao
) {

    private val _blockedDomains = MutableStateFlow<Set<String>>(emptySet())
    val blockedDomains: StateFlow<Set<String>> = _blockedDomains.asStateFlow()

    suspend fun refreshFromCache() {
        val policy = policyCacheDao.getCurrentPolicy()
        _blockedDomains.value = policy?.websiteLimits?.map { it.domain }?.toSet() ?: emptySet()
    }

    fun isDomainBlocked(domain: String): Boolean {
        val normalizedDomain = domain.removeSuffix(".")
        return _blockedDomains.value.any { blocked ->
            normalizedDomain == blocked || normalizedDomain.endsWith(".$blocked")
        }
    }

    suspend fun setBlockedDomains(domains: Set<String>) {
        _blockedDomains.value = domains
    }
}
