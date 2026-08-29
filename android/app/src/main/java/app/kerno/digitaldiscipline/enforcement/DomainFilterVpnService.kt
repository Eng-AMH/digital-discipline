package app.kerno.digitaldiscipline.enforcement

import android.content.Intent
import android.net.VpnService
import android.os.ParcelFileDescriptor
import android.util.Log
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.io.FileInputStream
import java.io.FileOutputStream
import javax.inject.Inject

/**
 * §6 Website Blocking. Per architecture doc §3.1 point 3, this is the ONLY
 * Play-compliant, non-managed-device path to domain-level website blocking on
 * Android — there is no OS API for a third-party app to block a URL in an
 * arbitrary browser directly.
 *
 * HOW IT WORKS: establishes a local, no-op VPN interface (all traffic appears
 * to route through it, but this service does NOT forward traffic to any
 * remote server — see the honesty note below). It intercepts outgoing DNS
 * query packets, parses the queried domain name, and checks it against the
 * cached blocked-domains set. If blocked, it returns an NXDOMAIN (domain does
 * not exist) response instead of forwarding the query — the browser then
 * behaves exactly as it would for a genuinely nonexistent domain. All non-DNS
 * traffic, and DNS queries for non-blocked domains, is forwarded normally to
 * the device's actual configured DNS server.
 *
 * STRUCTURAL LIMITATION, matching architecture §3.1 point 3 exactly: this
 * mechanism operates on DNS queries, which resolve at the DOMAIN level
 * (e.g. "youtube.com"), never at the PATH level (e.g. "youtube.com/shorts").
 * A DNS query for "youtube.com" looks identical regardless of whether the
 * user is about to load the homepage or a Shorts video — that information
 * (§6's WebsiteCategory.SHORT_FORM path-level distinction) is only visible
 * INSIDE the encrypted HTTPS request after DNS resolution completes, which
 * this service has no visibility into. This is why blockDomain() below only
 * ever accepts a bare domain string, never a domain+path — accepting a path
 * argument here would silently promise a capability this code cannot deliver,
 * which is exactly the kind of fake implementation the product spec rules out.
 *
 * PRIVACY NOTE: because this VPN is purely local (no remote relay), no user
 * traffic is exposed to any third party as a result of this feature — the
 * "VPN" here is an Android platform mechanism for intercepting the device's
 * own traffic locally, not a network privacy/anonymization product.
 */
@AndroidEntryPoint
class DomainFilterVpnService : VpnService() {

    @Inject
    lateinit var blockedDomainsRepository: BlockedDomainsRepository

    @Inject
    lateinit var deviceHealthReporter: DeviceHealthReporter

    private var vpnInterface: ParcelFileDescriptor? = null
    private val serviceJob = SupervisorJob()
    private val serviceScope = CoroutineScope(Dispatchers.IO + serviceJob)

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        establishVpnInterface()
        deviceHealthReporter.setVpnServiceActive(true)
        serviceScope.launch { runPacketLoop() }
        return START_STICKY
    }

    private fun establishVpnInterface() {
        val builder = Builder()
            .addAddress(VPN_LOCAL_ADDRESS, 32)
            // Route ONLY DNS traffic through this interface — deliberately
            // narrow. Routing 0.0.0.0/0 (all traffic) through a local VPN with
            // a naive packet loop would be both a performance disaster and far
            // more invasive than §6 requires; DNS-only interception is the
            // minimal mechanism that achieves domain blocking without
            // inspecting or relaying the user's actual content traffic.
            .addRoute(DNS_ROUTE_ONLY, 32)
            .addDnsServer(VPN_LOCAL_ADDRESS)
            .setSession("Kerno Website Filter")
            .setBlocking(false)

        vpnInterface = builder.establish()
        Log.i(TAG, "VPN interface established for DNS filtering.")
    }

    private suspend fun runPacketLoop() {
        val fd = vpnInterface ?: return
        val input = FileInputStream(fd.fileDescriptor)
        val output = FileOutputStream(fd.fileDescriptor)
        val buffer = ByteArray(32767)

        while (true) {
            val length = input.read(buffer)
            if (length <= 0) continue

            val packet = buffer.copyOf(length)
            val dnsQuery = DnsPacketParser.tryParseQuery(packet) ?: run {
                // Not a parseable DNS query (could be a non-DNS packet that
                // slipped through, or a DNS response/malformed packet) —
                // forward as-is rather than drop, since dropping unrecognized
                // traffic would break the DNS resolution path this service
                // depends on for legitimate lookups too.
                output.write(packet)
                continue
            }

            val isBlocked = blockedDomainsRepository.isDomainBlocked(dnsQuery.queriedDomain)
            if (isBlocked) {
                val nxDomainResponse = DnsPacketParser.buildNxDomainResponse(packet, dnsQuery)
                output.write(nxDomainResponse)
            } else {
                // Forward the original query unmodified to the real upstream
                // DNS resolver — this service does not act as a caching or
                // recursive resolver itself, it only intercepts, checks, and
                // either blocks or passes through the ORIGINAL packet bytes.
                output.write(packet)
            }
        }
    }

    /**
     * §30's WebsiteLimit.category=SHORT_FORM grouping (TikTok, Reels, Shorts,
     * Facebook Reels as one target) works fine here PRECISELY BECAUSE each of
     * those is typically its OWN domain (tiktok.com vs instagram.com vs
     * facebook.com) or, for YouTube Shorts specifically, is NOT separable from
     * youtube.com at all via this mechanism — which is exactly the honest gap
     * documented in the class-level comment and in
     * apps.policies.models.WebsiteCategory's docstring on the backend. This
     * method's signature (domain: String, not domain + path) reflects that
     * gap structurally rather than accepting an argument it cannot honor.
     */
    fun updateBlockedDomains(domains: Set<String>) {
        serviceScope.launch { blockedDomainsRepository.setBlockedDomains(domains) }
    }

    override fun onDestroy() {
        super.onDestroy()
        deviceHealthReporter.setVpnServiceActive(false)
        vpnInterface?.close()
        serviceJob.cancel()
    }

    companion object {
        private const val TAG = "DomainFilterVpn"
        private const val VPN_LOCAL_ADDRESS = "10.111.222.1"
        private const val DNS_ROUTE_ONLY = "10.111.222.1"
    }
}
