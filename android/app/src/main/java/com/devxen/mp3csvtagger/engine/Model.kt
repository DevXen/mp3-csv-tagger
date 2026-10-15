package com.devxen.mp3csvtagger.engine

/**
 * Core data types for the tagging engine.
 *
 * These mirror the desktop program's model exactly, because the two apps
 * share a file format and a set of rules (CSV layers, column roles, the
 * change log). Keeping the engine free of Android types is deliberate: it
 * lets the JVM unit tests exercise the real matching/layering rules without
 * an emulator.
 */

/** What a CSV column does. The integer values are part of the shared format. */
enum class Role(val value: Int) {
    /** A row applies only to files whose current value equals the CSV value. */
    Match(1),

    /** The CSV value replaces the file's value. */
    Write(2),

    /** The column is ignored. New columns start here. */
    Skip(3);

    companion object {
        fun fromValue(value: Int): Role = entries.firstOrNull { it.value == value } ?: Skip
    }
}

/** One CSV column: its heading (a tag name) and its role in that CSV layer. */
data class CsvTag(
    val name: String,
    var role: Role = Role.Skip,
)

/** One CSV file as a layer: headings plus parsed data rows. */
class CsvLayer(
    /** Stable id for this layer (on Android: the SAF document URI string). */
    val id: String,
    /** Display name (the file name). */
    val name: String,
    /** Column headings in file order; [tags] lines up with this list. */
    val headings: List<String>,
    /** Data rows as (1-based row index, values padded to the heading width). */
    val rows: List<IndexedRow>,
    /** False when the user has switched this layer off. */
    var included: Boolean = true,
) {
    /** Per-column roles, parallel to [headings]. New columns default to Skip. */
    val tags: MutableList<CsvTag> = headings.map { CsvTag(it) }.toMutableList()

    /** (zero-based column index, tag) pairs for one role, in column order. */
    fun columns(role: Role): List<IndexedValue<CsvTag>> =
        tags.withIndex().filter { it.value.role == role }
}

/** A CSV data row with its 1-based index in the file (used in the change log UI and candidate labels). */
data class IndexedRow(val index: Int, val values: List<String>)

/**
 * One MP3 file as the engine sees it: an id the UI can map back to a
 * document, a display name, and its current text tags.
 *
 * Tag keys are tag *names* in the shared sense: the ID3 frame id for
 * standard frames ("TIT2"), or the description for custom TXXX frames
 * ("Subgenre"). A file with no ID3 header simply has an empty map.
 */
data class Mp3Item(
    val id: String,
    val displayName: String,
    val tags: Map<String, String>,
    /**
     * True when the file carries embedded cover art (an APIC frame).
     * The image bytes are deliberately NOT part of the scan — they are
     * large, and tagging decisions (completeness, sync) only need to
     * know art is present. Mirrors the desktop Mp3File.has_cover.
     */
    val hasCover: Boolean = false,
    /**
     * An opaque token identifying the file's cover image (a hash of
     * the image bytes), supplied by the UI scan when it can compute
     * one, or null when it cannot. The engine never interprets the
     * token; [Sync] only compares tokens for equality to decide
     * whether two paired files carry the *same* cover. Null means
     * "unknown", never "no cover" — that is what [hasCover] says.
     */
    val coverKey: String? = null,
) {
    /** Current value for a CSV column, looked up by tag name, then by frame id. */
    fun valueFor(tagName: String, frame: String): String =
        tags[tagName] ?: tags[frame] ?: ""
}
