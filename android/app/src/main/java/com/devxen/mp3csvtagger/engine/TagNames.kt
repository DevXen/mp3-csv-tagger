package com.devxen.mp3csvtagger.engine

/**
 * Tag-name resolution: turning a CSV heading into the ID3 frame that will
 * actually be stored in the MP3. Same rules as the desktop program:
 *
 * 1. The heading *is* a known ID3 frame id ("TIT2") -> that frame.
 * 2. The heading is a friendly name ("Title", "Lead Performer", "Artist"),
 *    matched case-insensitively -> the mapped frame.
 * 3. Anything else -> a custom TXXX frame whose description is the heading
 *    itself ("Subgenre", "Rating", ...). Custom fields round-trip: the
 *    same heading reads the value back on the next run.
 */
object TagNames {

    /** Frame id -> friendly name. The user-facing half of the map. */
    val defaultAlternativeNames: Map<String, String> = linkedMapOf(
        "TPE1" to "Lead Performer",
        "TPE2" to "Band",
        "TPE3" to "Conductor",
        "TPUB" to "Publisher",
        "TIT2" to "Title",
        "TALB" to "Album",
        "TCON" to "Genre",
        "TYER" to "Year",
        "TDRC" to "Recording Date",
        "TRCK" to "Track Number",
        "TPOS" to "Disc Number",
        "TCOM" to "Composer",
        "TPE4" to "Remixer",
        "TIT1" to "Grouping",
        "TIT3" to "Subtitle",
        "TBPM" to "BPM",
        "TKEY" to "Key",
        "TLAN" to "Language",
        "TCOP" to "Copyright",
        "TENC" to "Encoded By",
        "TEXT" to "Lyricist",
        "COMM" to "Comment",
        "USLT" to "Lyrics",
    )

    /** Extra accepted aliases; accepted on input, never shown as the name. */
    private val extraAliases: Map<String, String> = mapOf(
        "artist" to "TPE1",
        "performer" to "TPE1",
        "album artist" to "TPE2",
        "date" to "TDRC",
        "track" to "TRCK",
        "disc" to "TPOS",
    )

    /**
     * ID3v2 frame ids recognised as "a real frame" for rule 1. (The desktop
     * checks its tag library's class table; this is the equivalent list.)
     */
    private val knownFrames: Set<String> = setOf(
        "AENC", "APIC", "ASPI", "COMM", "COMR", "ENCR", "EQU2", "ETCO", "GEOB",
        "GRID", "LINK", "MCDI", "MLLT", "OWNE", "PRIV", "PCNT", "PLAY", "POPM",
        "POSS", "RBUF", "RVAD", "RVRB", "SEEK", "SIGN", "SYLT", "SYTC", "TALB",
        "TBPM", "TCOM", "TCON", "TCOP", "TDEN", "TDLY", "TDOR", "TDRL", "TDRC",
        "TDES", "TEXT", "TFLT", "TGID", "TIT1", "TIT2", "TIT3", "TKEY", "TLAN",
        "TLEN", "TMCL", "TMED", "TMOO", "TOAL", "TOFN", "TOLY", "TOPE", "TOWN",
        "TPE1", "TPE2", "TPE3", "TPE4", "TPOS", "TPRO", "TPUB", "TRCK", "TRDA",
        "TRSN", "TRSO", "TSIZ", "TSRC", "TSSE", "TSST", "TXXX", "TYER", "UFID",
        "USER", "USLT", "WCOM", "WCOP", "WOAF", "WOAR", "WOAS", "WORS", "WPAY",
        "WPUB", "WXXX",
    )

    /** Frames that never carry editable text for us; skipped when reading. */
    val ignoredFrames: Set<String> = setOf("PRIV", "APIC")

    /** Resolve a CSV heading / tag name to a frame id (or "TXXX"). */
    fun frameForTagName(
        tagName: String,
        alternativeNames: Map<String, String> = defaultAlternativeNames,
    ): String {
        val name = tagName.trim()
        if (name.isEmpty()) return "TXXX"
        val upper = name.uppercase()
        if (upper.startsWith("TXXX:")) return "TXXX"
        if (upper.length == 4 && upper in knownFrames) return upper
        for ((frame, friendly) in alternativeNames) {
            if (friendly.equals(name, ignoreCase = true)) return frame.uppercase()
        }
        extraAliases[name.lowercase()]?.let { return it }
        return "TXXX"
    }
}
