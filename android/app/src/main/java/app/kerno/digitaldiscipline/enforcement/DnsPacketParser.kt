package app.kerno.digitaldiscipline.enforcement

/**
 * Minimal DNS packet parsing sufficient for this service's needs: extract the
 * queried domain name from a UDP DNS query packet, and construct a valid
 * NXDOMAIN response for a blocked domain.
 *
 * HONESTY FLAG, more important here than almost anywhere else in this codebase:
 * this is raw binary protocol parsing (RFC 1035), which is exactly the kind of
 * code where a subtle bug does not fail loudly — it can silently corrupt or
 * drop DNS traffic, breaking ALL internet connectivity on the device (not just
 * the website-blocking feature), in a way that would be confusing to debug
 * without knowing this VPN service is the cause. This has NOT been tested
 * against real DNS traffic captures in this environment (no way to generate
 * or verify real UDP packet bytes without a running Android device/emulator).
 * Before this ships, README.md's testing checklist requires: (1) verifying
 * against a packet capture (e.g. Wireshark) of real DNS queries on a test
 * device, (2) confirming normal (non-blocked) browsing is completely
 * unaffected — since a bug here is far more likely to break unrelated
 * browsing than to fail to block a domain, (3) testing IPv6 (AAAA) queries
 * specifically, which this simplified parser does not fully differentiate
 * from A queries — see the TODO below, (4) implementing and verifying the UDP
 * checksum recalculation flagged as an explicit gap in buildNxDomainResponse.
 *
 * SCOPE LIMITATION, intentional: this parser only handles the single most
 * common real-world case — one question per packet, no DNS compression
 * pointers in the QUESTION section (compression pointers are used in
 * RESPONSES far more than in queries from a typical mobile OS resolver, so
 * their absence in the question section is a reasonable simplifying
 * assumption for THIS traffic pattern, but is flagged as an assumption, not a
 * guarantee of the DNS spec in general).
 */
object DnsPacketParser {

    private const val UDP_HEADER_SIZE = 8
    private const val IP_HEADER_MIN_SIZE = 20
    private const val DNS_HEADER_SIZE = 12
    private const val DNS_TYPE_A = 1
    private const val DNS_TYPE_AAAA = 28
    private const val PROTOCOL_UDP = 17

    data class ParsedDnsQuery(
        val queriedDomain: String,
        val dnsPayloadOffset: Int,
        val transactionId: ByteArray,
        val questionSectionBytes: ByteArray,
        val queryType: Int
    )

    /**
     * Returns null if this packet is not a well-formed, single-question UDP
     * DNS query — callers (DomainFilterVpnService) treat null as "forward
     * unmodified," which is the SAFE default: when in doubt, don't touch the
     * packet, since forwarding an unrecognized packet unmodified can only ever
     * fail to filter (missing a block), never break unrelated traffic —
     * whereas attempting to parse/rewrite a packet this parser doesn't fully
     * understand could produce a malformed packet and break connectivity.
     */
    fun tryParseQuery(rawPacket: ByteArray): ParsedDnsQuery? {
        return try {
            parseQueryUnsafe(rawPacket)
        } catch (e: Exception) {
            null
        }
    }

    private fun parseQueryUnsafe(rawPacket: ByteArray): ParsedDnsQuery? {
        // IP header: first 4 bits of byte 0 is the IP version. Only IPv4 UDP
        // packets are handled — IPv6 has a fixed 40-byte header and a
        // different next-header field position; not handled by this
        // simplified parser (see TODO in class doc comment).
        if (rawPacket.size < IP_HEADER_MIN_SIZE) return null
        val ipVersion = (rawPacket[0].toInt() shr 4) and 0x0F
        if (ipVersion != 4) return null // IPv6 not handled by this simplified parser

        val ipHeaderLength = (rawPacket[0].toInt() and 0x0F) * 4
        val protocol = rawPacket[9].toInt() and 0xFF
        if (protocol != PROTOCOL_UDP) return null

        val udpStart = ipHeaderLength
        if (rawPacket.size < udpStart + UDP_HEADER_SIZE) return null

        val destPort = ((rawPacket[udpStart + 2].toInt() and 0xFF) shl 8) or (rawPacket[udpStart + 3].toInt() and 0xFF)
        if (destPort != 53) return null // not a DNS query (wrong destination port)

        val dnsStart = udpStart + UDP_HEADER_SIZE
        if (rawPacket.size < dnsStart + DNS_HEADER_SIZE) return null

        val transactionId = rawPacket.copyOfRange(dnsStart, dnsStart + 2)
        val flags = ((rawPacket[dnsStart + 2].toInt() and 0xFF) shl 8) or (rawPacket[dnsStart + 3].toInt() and 0xFF)
        val isQuery = (flags shr 15) and 0x1 == 0 // QR bit: 0 = query, 1 = response
        if (!isQuery) return null

        val questionCount = ((rawPacket[dnsStart + 4].toInt() and 0xFF) shl 8) or (rawPacket[dnsStart + 5].toInt() and 0xFF)
        if (questionCount != 1) return null // simplifying assumption, documented in class comment

        // Parse the QNAME: a sequence of length-prefixed labels terminated by
        // a zero-length label. E.g. "example.com" encodes as:
        //   [7]example[3]com[0]
        var pos = dnsStart + DNS_HEADER_SIZE
        val domainBuilder = StringBuilder()
        while (pos < rawPacket.size) {
            val labelLength = rawPacket[pos].toInt() and 0xFF
            if (labelLength == 0) {
                pos += 1
                break
            }
            if (labelLength and 0xC0 == 0xC0) {
                // DNS name compression pointer encountered in the question
                // section — explicitly NOT supported by this simplified
                // parser (see class doc comment's scope limitation). Bail out
                // safely rather than mis-parse.
                return null
            }
            pos += 1
            if (pos + labelLength > rawPacket.size) return null
            if (domainBuilder.isNotEmpty()) domainBuilder.append('.')
            domainBuilder.append(String(rawPacket, pos, labelLength, Charsets.US_ASCII))
            pos += labelLength
        }

        if (pos + 4 > rawPacket.size) return null // QTYPE (2 bytes) + QCLASS (2 bytes)
        val queryType = ((rawPacket[pos].toInt() and 0xFF) shl 8) or (rawPacket[pos + 1].toInt() and 0xFF)
        // TODO(device-testing): AAAA (IPv6, type 28) queries are parsed
        // identically to A (type 1) queries here — the domain name extraction
        // logic doesn't differ by query type, so this is likely fine, but
        // real-device testing should confirm blocking behaves correctly for
        // apps/browsers that prefer IPv6 and issue AAAA queries first.
        if (queryType != DNS_TYPE_A && queryType != DNS_TYPE_AAAA) return null

        val questionSectionEnd = pos + 4
        val questionSectionBytes = rawPacket.copyOfRange(dnsStart + DNS_HEADER_SIZE, questionSectionEnd)

        return ParsedDnsQuery(
            queriedDomain = domainBuilder.toString().lowercase(),
            dnsPayloadOffset = dnsStart,
            transactionId = transactionId,
            questionSectionBytes = questionSectionBytes,
            queryType = queryType
        )
    }

    /**
     * Builds a minimal DNS response packet with RCODE=3 (NXDOMAIN), echoing
     * the original transaction ID and question section (required — DNS
     * clients match responses to queries by transaction ID AND typically
     * validate the echoed question section matches what they asked).
     *
     * EXPLICIT INCOMPLETE-WORK FLAG: this constructs the DNS payload
     * correctly but does NOT recalculate the UDP checksum for the
     * synthesized response — see the detailed comment inline below at the
     * checksum-zeroing step for why zeroing (rather than leaving stale) is
     * the safe interim choice, and why real checksum calculation is required
     * before this can be trusted. An incorrect/stale checksum here would
     * likely cause the OS network stack to silently DROP the response,
     * observable as "blocked domains time out instead of failing fast" — a
     * real bug to catch in device testing, not a theoretical concern.
     */
    fun buildNxDomainResponse(originalPacket: ByteArray, query: ParsedDnsQuery): ByteArray {
        val ipHeaderLength = (originalPacket[0].toInt() and 0x0F) * 4
        val udpStart = ipHeaderLength
        val dnsStart = query.dnsPayloadOffset

        val responseHeader = ByteArray(DNS_HEADER_SIZE)
        query.transactionId.copyInto(responseHeader, 0)
        // Flags: QR=1 (response), Opcode=0, AA=0, TC=0, RD=1 (recursion
        // desired, echoing typical client requests), RA=0, Z=0, RCODE=3 (NXDOMAIN)
        responseHeader[2] = 0x81.toByte() // 1000 0001: QR=1, RD=1
        responseHeader[3] = 0x83.toByte() // 1000 0011: RA=0, RCODE=0011=3 (NXDOMAIN)
        responseHeader[4] = 0x00; responseHeader[5] = 0x01 // QDCOUNT=1
        responseHeader[6] = 0x00; responseHeader[7] = 0x00 // ANCOUNT=0
        responseHeader[8] = 0x00; responseHeader[9] = 0x00 // NSCOUNT=0
        responseHeader[10] = 0x00; responseHeader[11] = 0x00 // ARCOUNT=0

        val dnsPayload = responseHeader + query.questionSectionBytes
        val responsePacket = originalPacket.copyOfRange(0, dnsStart) + dnsPayload

        val udpLengthFieldOffset = udpStart + 4
        val newUdpLength = 8 + dnsPayload.size
        if (udpLengthFieldOffset + 1 < responsePacket.size) {
            responsePacket[udpLengthFieldOffset] = ((newUdpLength shr 8) and 0xFF).toByte()
            responsePacket[udpLengthFieldOffset + 1] = (newUdpLength and 0xFF).toByte()
        }
        // UDP checksum recalculation is INTENTIONALLY LEFT AS AN EXPLICIT GAP,
        // not silently skipped. Zeroing the checksum field (0x0000) is
        // technically valid per RFC 768 for IPv4 UDP — a zero checksum means
        // "no checksum computed," which some network stacks accept and some
        // (particularly if any NAT/middlebox-like processing happens between
        // this VPN TUN interface and the app) may not. This is the safe,
        // honest interim choice rather than leaving the ORIGINAL query
        // packet's now-stale checksum in place, which would definitely be
        // wrong. Full checksum computation (over the UDP pseudo-header
        // including source/dest IP) should be implemented and verified on a
        // real device before this ships — see class doc comment's testing list.
        val udpChecksumOffset = udpStart + 6
        if (udpChecksumOffset + 1 < responsePacket.size) {
            responsePacket[udpChecksumOffset] = 0x00
            responsePacket[udpChecksumOffset + 1] = 0x00
        }

        return responsePacket
    }
}
