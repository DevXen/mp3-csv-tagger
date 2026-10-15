package com.devxen.mp3csvtagger.engine

/**
 * Value normalisation for Match columns — the heart of "does this CSV row
 * belong to this MP3 file?".
 *
 * The rule (identical to the desktop program): trim, lower-case, and delete
 * every ASCII punctuation character. So "Rage Against the Machine",
 * "rage against the machine" and "Rage Against The Machine!" all match,
 * while different words never do.
 *
 * Values are normalised once and memoised: matching builds a hash index of
 * normalised keys (see [buildPreview]), so a library scan stays linear
 * instead of re-cleaning the same strings for every row/file pair.
 */
object Matching {

    /** ASCII punctuation: !"#$%&'()*+,-./:;<=>?@[\]^_`{|}~ */
    private val punctuation: Set<Char> =
        ("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~").toSet()

    private val cache = HashMap<String, String>()

    fun normalize(value: String?): String {
        if (value.isNullOrEmpty()) return ""
        cache[value]?.let { return it }
        val result = buildString(value.length) {
            for (ch in value.trim().lowercase()) {
                if (ch !in punctuation) append(ch)
            }
        }.trim()
        // The cache is only touched from the (single-threaded) preview build
        // and from tests; a plain HashMap is enough and keeps this honest.
        cache[value] = result
        return result
    }
}
