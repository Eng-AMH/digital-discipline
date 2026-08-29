package app.kerno.digitaldiscipline.data.crypto

import org.json.JSONArray
import org.json.JSONObject

/**
 * Produces canonical JSON matching the server's exact serialization contract,
 * documented in apps.policies.services._canonical_json on the backend:
 *
 *   json.dumps(payload, sort_keys=True, separators=(",", ":"))
 *
 * This means:
 *   1. Object keys sorted lexicographically (ASCII/codepoint order)
 *   2. No whitespace after ':' or ','
 *   3. Standard JSON string escaping (matches Python's json module defaults)
 *
 * WHY THIS CANNOT USE MOSHI DIRECTLY: Moshi serializes fields in the order
 * declared in the data class (or annotation order), not sorted order, and
 * @JsonClass-generated adapters have no built-in "canonical/sorted" mode. Using
 * Moshi's default output here would produce valid JSON that represents the same
 * data but differs byte-for-byte from what the server signed — which would make
 * EVERY signature verification fail, silently, with no indication that the data
 * itself was correct and only the serialization convention differed. This
 * class exists specifically to avoid that failure mode: it operates on a plain
 * `Map<String, Any?>` / `JSONObject`, not a typed data class, and sorts keys
 * explicitly at every level of nesting.
 *
 * HONEST VERIFICATION STATUS: the underlying cryptographic round-trip (a
 * device-generated Ed25519 key signing canonical JSON bytes, verified against
 * that same canonical string) WAS verified server-side during backend
 * development — see the earlier Ed25519 sanity check in this build session.
 *
 * For THIS specific canonicalization algorithm, since no JVM/Android toolchain
 * is available in this environment to compile and run the actual Kotlin file,
 * I built a faithful line-by-line Python simulation of this exact algorithm
 * (same key-sorting, same per-character escaping rules, same UTF-16-code-unit
 * iteration model) and ran it against Python's real `json.dumps(sort_keys=True,
 * separators=(",",":"))` across: key-order shuffling, nested objects, arrays
 * (confirmed NOT sorted), an Arabic-text field (this product's source spec is
 * in Arabic, so non-ASCII display names are a real case, not a hypothetical),
 * a 🔥 emoji (a non-BMP character requiring a UTF-16 surrogate pair — confirmed
 * that Kotlin's per-Char iteration, which walks UTF-16 code units rather than
 * Unicode codepoints, coincidentally produces the exact same surrogate-pair
 * \\uXXXX\\uXXXX escape sequence Python emits, with no special-case code
 * needed), and a realistic unlock-token-shaped payload. All cases produced
 * byte-identical output to Python's json.dumps. This is meaningfully stronger
 * evidence than "reasoned through it," but it is still a simulation of the
 * algorithm, not a compiled-and-run test of this actual .kt file — that step
 * still needs to happen in Android Studio against a real backend response,
 * and is listed as the first item in README.md's device-testing checklist.
 */
object CanonicalJson {

    /**
     * Recursively builds a canonical JSON string from any JSON-compatible
     * value: Map (→ object, keys sorted), List (→ array, order preserved —
     * arrays are never sorted, only object keys), String, Number, Boolean, null.
     */
    fun encode(value: Any?): String {
        val builder = StringBuilder()
        writeValue(value, builder)
        return builder.toString()
    }

    private fun writeValue(value: Any?, builder: StringBuilder) {
        when (value) {
            null -> builder.append("null")
            is Map<*, *> -> writeObject(value, builder)
            is List<*> -> writeArray(value, builder)
            is String -> writeString(value, builder)
            is Boolean -> builder.append(if (value) "true" else "false")
            is Int -> builder.append(value.toString())
            is Long -> builder.append(value.toString())
            // Python's json.dumps renders floats without a trailing ".0" only
            // when the value is a genuine int; since our payloads' numeric
            // fields (granted_minutes, daily_minutes, etc.) are always ints on
            // both sides of the wire, Double is intentionally NOT given special
            // float-formatting handling here — if a Double ever needs to be
            // canonicalized, this is the place to add Python-compatible
            // formatting (repr-style), not before, since guessing at that
            // format without a concrete need would be more likely to introduce
            // a subtle mismatch than to prevent one.
            is Double -> builder.append(
                if (value == value.toLong().toDouble()) value.toLong().toString() else value.toString()
            )
            is JSONObject -> writeObject(jsonObjectToMap(value), builder)
            is JSONArray -> writeArray(jsonArrayToList(value), builder)
            else -> throw IllegalArgumentException(
                "CanonicalJson.encode does not support type ${value::class.java.name}. " +
                    "Only Map, List, String, Boolean, Int, Long, Double, and null are supported, " +
                    "matching the set of JSON-native types the server's json.dumps handles."
            )
        }
    }

    private fun writeObject(map: Map<*, *>, builder: StringBuilder) {
        // Keys sorted lexicographically — this is THE critical line. Python's
        // sort_keys=True sorts by Unicode codepoint, which for the ASCII-only
        // field names used in this app's payloads (snake_case English
        // identifiers) is identical to Kotlin's default String comparison —
        // both compare by UTF-16 code unit, which agrees with codepoint order
        // for the entire ASCII range these keys live in.
        val sortedKeys = map.keys.map { it.toString() }.sorted()
        builder.append('{')
        sortedKeys.forEachIndexed { index, key ->
            if (index > 0) builder.append(',')
            writeString(key, builder)
            builder.append(':')
            writeValue(map[key], builder)
        }
        builder.append('}')
    }

    private fun writeArray(list: List<*>, builder: StringBuilder) {
        builder.append('[')
        list.forEachIndexed { index, item ->
            if (index > 0) builder.append(',')
            writeValue(item, builder)
        }
        builder.append(']')
    }

    /**
     * Matches Python json.dumps' default string escaping: backslash, double
     * quote, and control characters (0x00-0x1F) are escaped; non-ASCII
     * Unicode is ALSO escaped as \\uXXXX, because the server's
     * _canonical_json call uses json.dumps with its default ensure_ascii=True
     * (it is never passed ensure_ascii=False). This matters concretely: if any
     * payload field contains non-ASCII text (e.g. a display_name with Arabic
     * characters, which this product must support since the source spec itself
     * is in Arabic), this method MUST escape non-ASCII as \\uXXXX to match, or
     * verification would fail for any user with a non-ASCII display name in a
     * signed payload. Handled explicitly below rather than left as a
     * latent bug that would only surface for non-English-named users.
     */
    private fun writeString(value: String, builder: StringBuilder) {
        builder.append('"')
        for (char in value) {
            when {
                char == '\\' -> builder.append("\\\\")
                char == '"' -> builder.append("\\\"")
                char == '\n' -> builder.append("\\n")
                char == '\r' -> builder.append("\\r")
                char == '\t' -> builder.append("\\t")
                char.code < 0x20 -> builder.append("\\u%04x".format(char.code))
                char.code > 0x7E -> builder.append("\\u%04x".format(char.code))
                else -> builder.append(char)
            }
        }
        builder.append('"')
    }

    private fun jsonObjectToMap(obj: JSONObject): Map<String, Any?> {
        val result = LinkedHashMap<String, Any?>()
        obj.keys().forEach { key -> result[key] = obj.get(key) }
        return result
    }

    private fun jsonArrayToList(arr: JSONArray): List<Any?> =
        (0 until arr.length()).map { arr.get(it) }
}
