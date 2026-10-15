package com.devxen.mp3csvtagger.engine

/**
 * Building the preview: which files match which CSV rows, and what would
 * change. This is a direct port of the desktop engine's algorithm:
 *
 * 1. Each file's tags are already in memory (scanned once).
 * 2. For each CSV layer, a **hash index** maps the normalised Match-key of
 *    every file to the file itself, so a CSV row finds its files with one
 *    lookup. Nothing is compared row-by-file in a nested loop.
 * 3. Layers run in order. After a layer, its selected writes become the
 *    files' *effective* values, so a later layer can Match on a value an
 *    earlier layer is going to write.
 *
 * A [FilenamePatternSource] can sit in the same layer list: instead of CSV
 * rows it derives each file's values from its own folder/file name, matched
 * per-file by construction. So can a [ValuesSource]: ready-made values
 * computed by another feature (tag sync), keyed by item id.
 */

/**
 * Display value used as a cover-art cell's "old value" when a file
 * already has embedded art. The image bytes are never loaded for a
 * preview; presence is all a change decision needs. (Same marker the
 * desktop preview uses.)
 */
const val COVER_PRESENT = "[cover image]"

/**
 * Source name recorded on a candidate the user typed into the preview
 * by hand (an inline manual edit). It shows up wherever a candidate's
 * source is displayed — including the change log — so a hand-typed
 * value is always distinguishable from a CSV value.
 */
const val MANUAL_SOURCE = "manual edit"

/**
 * Layer number for manual edits. Real layers are numbered by their
 * position in the layer list, so a layer of a million sorts a manual
 * edit after every value any layer could produce: the value the user
 * typed most recently is the one that wins.
 */
const val MANUAL_LAYER = 1_000_000

/** One value a CSV row (or pattern) wants to write, and where it came from. */
data class Candidate(
    val value: String,
    val sourceName: String,
    val sourceRow: Int,
    val layer: Int,
    /**
     * True only for a value the user typed into the preview by hand
     * (see [Cell.setManualEdit]). Manual candidates are kept distinct
     * from layered candidates so they can be replaced or cleared
     * without disturbing the values the layers produced.
     */
    val manual: Boolean = false,
)

/** All candidate values for one (file, tag), with one selected. */
class Cell(
    val tagName: String,
    val frame: String,
    /** The value currently stored in the file. */
    val oldValue: String,
) {
    val candidates: MutableList<Candidate> = mutableListOf()

    /** Index into [candidates]; the newest layer's value wins by default. */
    var selected: Int = 0

    val value: String get() = if (candidates.isEmpty()) oldValue else candidates[selected].value
    val changed: Boolean get() = candidates.isNotEmpty() && value != oldValue
    val hasMultiple: Boolean get() = candidates.size > 1

    /** Add a candidate; identical values merge, and the newest is selected. */
    fun addCandidate(candidate: Candidate) {
        val existing = candidates.indexOfFirst { it.value == candidate.value }
        if (existing >= 0) {
            selected = existing
            return
        }
        candidates += candidate
        selected = candidates.lastIndex
    }

    /**
     * The manual-edit candidate on this cell, or null. At most one
     * manual candidate ever exists per cell — [setManualEdit] replaces
     * it rather than stacking edits.
     */
    val manualCandidate: Candidate? get() = candidates.firstOrNull { it.manual }

    /**
     * Record a value the user typed into this cell by hand.
     *
     * Any previous manual candidate is dropped, the new value is
     * appended as a manual candidate (source [MANUAL_SOURCE], layer
     * [MANUAL_LAYER]) and selected. Because a manual edit is an
     * ordinary selected candidate from this point on, Apply, the
     * change log and snapshot undo all handle it with no special
     * cases — the log simply records its source as "manual edit".
     */
    fun setManualEdit(value: String) {
        candidates.removeAll { it.manual }
        candidates += Candidate(value, MANUAL_SOURCE, -1, MANUAL_LAYER, manual = true)
        selected = candidates.lastIndex
    }

    /**
     * Remove the manual edit, re-selecting the last remaining value.
     *
     * The candidates the layers produced are still on the cell, so
     * clearing an edit falls back to the newest of them (the same
     * value that would have been selected had the edit never
     * happened). A no-op when the cell has no manual candidate.
     */
    fun clearManualEdit() {
        if (manualCandidate == null) return
        candidates.removeAll { it.manual }
        selected = if (candidates.isEmpty()) 0 else candidates.lastIndex
    }
}

/** One matched file and everything the run would write to it. */
class PreviewRow(
    val itemId: String,
    val displayName: String,
) {
    /** Match column tag name -> the file's value that matched (display only). */
    val matches: MutableMap<String, String> = mutableMapOf()

    /** Write cells keyed by tag name, in first-use order. */
    val cells: LinkedHashMap<String, Cell> = linkedMapOf()

    val changeCount: Int get() = cells.values.count { it.changed }
}

/** The whole preview: rows for matched files only. */
class Preview(
    val rows: List<PreviewRow>,
    /** Write-column tag names in the order the layers first use them. */
    val writeTags: List<String>,
    val filesScanned: Int,
    val scanErrors: List<String>,
) {
    val filesMatched: Int get() = rows.size
    val totalChanges: Int get() = rows.sumOf { it.changeCount }
    fun rowForItem(itemId: String): PreviewRow? = rows.firstOrNull { it.itemId == itemId }
}

/**
 * A layer in the stack: a CSV file, a filename-pattern source, or a
 * virtual values source.
 *
 * This is deliberately a plain interface, not a sealed one: layer kinds
 * are added by engine work in their own changes, while the screens that
 * hold a layer list are edited separately. A sealed type would make
 * every exhaustive `when` over layers in already-shipped UI code fail
 * to compile the moment the engine gained a kind — the UI adds its
 * branches for a new kind when it learns to *present* that kind, and
 * until then the kind simply has no row in the layer list.
 */
interface LayerSource {
    val name: String
    val included: Boolean
}

/** Adapter so a [CsvLayer] can sit in the preview's layer list. */
data class CsvSource(val csv: CsvLayer) : LayerSource {
    override val name: String get() = csv.name
    override val included: Boolean get() = csv.included
}

/**
 * A filename-pattern source: derives tag values from each file's folder
 * path and file name. Pattern segments are separated by `/`; a segment is
 * either a literal (must equal that path segment, case-insensitively) or
 * one or more `{Tag Name}` placeholders with literal text between them,
 * e.g. "{Artist}/{Album}/{Track} - {Title}". The last segment matches the
 * file name without its ".mp3" extension.
 */
data class FilenamePatternSource(
    val pattern: String,
    override val included: Boolean = true,
) : LayerSource {
    override val name: String get() = "Filename pattern: $pattern"
}

/**
 * A virtual layer of ready-made write values, keyed by item id:
 * `itemId -> (tag name -> value)`.
 *
 * This is the generic path for any feature that computes values itself
 * instead of reading them from a CSV or a file name — tag sync
 * (see [buildSyncValues]) is the first user. Feeding the values through
 * the ordinary preview machinery means the user sees every proposed
 * change, can pick candidates and override them with manual edits, and
 * gets the usual change log and snapshot undo on apply — no feature
 * built on this needs its own apply path. It mirrors the desktop
 * preview's value-layer helper (`add_value_layer`).
 *
 * Values are taken exactly as given: deciding *which* values are worth
 * proposing (non-empty, different from the file's current value, …) is
 * the producing feature's job, not this layer's.
 */
data class ValuesSource(
    override val name: String,
    val valuesByItemId: Map<String, Map<String, String>>,
    override val included: Boolean = true,
) : LayerSource

/**
 * Match a pattern against a relative path (folder names + file name).
 * Returns the captured tag values, or null when the literals do not match.
 * If the pattern has fewer segments than the path, it anchors to the END
 * of the path (the file name and its nearest folders) — the common case,
 * since libraries nest deeper than any one pattern describes.
 */
fun matchFilenamePattern(pattern: String, relativePath: String): Map<String, String>? {
    val patternSegments = pattern.trim().split('/').filter { it.isNotEmpty() }
    val pathSegments = relativePath.split('/').filter { it.isNotEmpty() }.toMutableList()
    if (pathSegments.isEmpty() || patternSegments.isEmpty()) return null
    // Strip the .mp3 extension from the file-name segment before matching.
    val last = pathSegments.lastIndex
    pathSegments[last] = pathSegments[last].replace(Regex("(?i)\\.mp3$"), "")
    if (patternSegments.size > pathSegments.size) return null
    val aligned = pathSegments.takeLast(patternSegments.size)
    val captures = linkedMapOf<String, String>()
    for ((patternSegment, pathSegment) in patternSegments.zip(aligned)) {
        if (!matchSegment(patternSegment, pathSegment, captures)) return null
    }
    return captures
}

/** Match one path segment against one pattern segment, recording captures. */
private fun matchSegment(pattern: String, segment: String, captures: MutableMap<String, String>): Boolean {
    // Build a regex from the pattern segment: literals are quoted, each
    // {Placeholder} becomes a capture group.
    val names = mutableListOf<String>()
    val regex = StringBuilder("^")
    var i = 0
    while (i < pattern.length) {
        val open = pattern.indexOf('{', i)
        if (open < 0) {
            regex.append(Regex.escape(pattern.substring(i)))
            i = pattern.length
        } else {
            regex.append(Regex.escape(pattern.substring(i, open)))
            val close = pattern.indexOf('}', open)
            if (close < 0) return false
            names += pattern.substring(open + 1, close).trim()
            // Non-greedy unless this is the last placeholder with no literal
            // after it, in which case it takes the rest of the segment.
            val rest = pattern.substring(close + 1)
            regex.append(if (rest.isEmpty()) "(.+)" else "(.+?)")
            i = close + 1
        }
    }
    regex.append("$")
    val match = Regex(regex.toString(), RegexOption.IGNORE_CASE).matchEntire(segment) ?: return false
    for ((index, name) in names.withIndex()) {
        if (name.isNotEmpty()) captures[name] = match.groupValues[index + 1].trim()
    }
    return true
}

/**
 * Compute the full preview. [layers] are CSV and/or filename-pattern
 * sources, in order; [files] are the scanned items; [alternativeNames] is
 * the friendly-name map used to resolve headings to frames.
 */
fun buildPreview(
    layers: List<LayerSource>,
    files: List<Mp3Item>,
    scanErrors: List<String> = emptyList(),
    alternativeNames: Map<String, String> = TagNames.defaultAlternativeNames,
    /**
     * Relative paths ("Folder/Sub/01 - Song.mp3") per item id, used by
     * filename-pattern layers. Supplied by the scanner (paths are a
     * storage concern, so they travel beside [Mp3Item], not inside it).
     */
    relativePaths: Map<String, String> = emptyMap(),
): Preview {
    val rowsById = LinkedHashMap<String, PreviewRow>()
    val writeTags = mutableListOf<String>()

    // Effective values per file: starts as the on-disk tags, updated after
    // each layer with that layer's selected writes (see header comment).
    val effective = HashMap<String, MutableMap<String, String>>()
    for (file in files) effective[file.id] = HashMap(file.tags)
    val byId = files.associateBy { it.id }

    fun effectiveValue(itemId: String, tagName: String, frame: String): String {
        val tags = effective[itemId] ?: return ""
        return tags[tagName] ?: tags[frame] ?: ""
    }

    fun rowFor(itemId: String): PreviewRow =
        rowsById.getOrPut(itemId) { PreviewRow(itemId, byId.getValue(itemId).displayName) }

    fun addWrite(row: PreviewRow, item: Mp3Item, tagName: String, value: String, sourceName: String, sourceRow: Int, layer: Int) {
        val frame = TagNames.frameForTagName(tagName, alternativeNames)
        val cell = row.cells.getOrPut(tagName) {
            // Cover art is not a text tag, so there is no stored text
            // value to compare against: the "old value" is the presence
            // marker when the file already has art (the desktop
            // preview's rule), which also makes `changed` come out
            // right for a cover replacement.
            val oldValue = if (frame == "APIC") {
                if (item.hasCover) COVER_PRESENT else ""
            } else {
                item.valueFor(tagName, frame)
            }
            Cell(tagName, frame, oldValue)
        }
        cell.addCandidate(Candidate(value, sourceName, sourceRow, layer))
        if (tagName !in writeTags) writeTags += tagName
    }

    layers.forEachIndexed { layer, source ->
        if (!source.included) return@forEachIndexed
        when (source) {
            is CsvSource -> {
                val csv = source.csv
                val matchCols = csv.columns(Role.Match)
                val writeCols = csv.columns(Role.Write)
                if (writeCols.isEmpty()) return@forEachIndexed

                // Hash index: normalised match key -> file ids.
                val index: HashMap<List<String>, MutableList<String>>? =
                    if (matchCols.isEmpty()) null else HashMap<List<String>, MutableList<String>>().also { idx ->
                        for (file in files) {
                            val key = matchCols.map { (colIndex, tag) ->
                                val frame = TagNames.frameForTagName(tag.name, alternativeNames)
                                Matching.normalize(effectiveValue(file.id, tag.name, frame))
                            }
                            idx.getOrPut(key) { mutableListOf() } += file.id
                        }
                    }

                for (row in csv.rows) {
                    val targetIds: List<String> = if (index == null) {
                        files.map { it.id } // no Match columns: applies to every file
                    } else {
                        val key = matchCols.map { (colIndex, _) -> Matching.normalize(row.values[colIndex]) }
                        index[key] ?: emptyList()
                    }
                    for (itemId in targetIds) {
                        val item = byId.getValue(itemId)
                        val previewRow = rowFor(itemId)
                        for ((_, tag) in matchCols) {
                            val frame = TagNames.frameForTagName(tag.name, alternativeNames)
                            previewRow.matches[tag.name] = effectiveValue(itemId, tag.name, frame)
                        }
                        for ((colIndex, tag) in writeCols) {
                            addWrite(previewRow, item, tag.name, row.values[colIndex], csv.name, row.index, layer)
                        }
                    }
                }
            }
            is FilenamePatternSource -> {
                for (item in files) {
                    val relativePath = relativePaths[item.id] ?: item.displayName
                    val captures = matchFilenamePattern(source.pattern, relativePath) ?: continue
                    val previewRow = rowFor(item.id)
                    for ((tagName, value) in captures) {
                        if (value.isNotEmpty()) {
                            addWrite(previewRow, item, tagName, value, source.name, 0, layer)
                        }
                    }
                }
            }
            is ValuesSource -> {
                // Ready-made values keyed by item id. Ids that are not
                // in this scan are skipped (the values were computed
                // against some scan; a stale id must not invent a row
                // for a file that is not here).
                for ((itemId, values) in source.valuesByItemId) {
                    val item = byId[itemId] ?: continue
                    val previewRow = rowFor(itemId)
                    for ((tagName, value) in values) {
                        addWrite(previewRow, item, tagName, value, source.name, 0, layer)
                    }
                }
            }
        }
        // This layer's selected writes become effective for the next layer.
        for (row in rowsById.values) {
            for ((tagName, cell) in row.cells) {
                if (cell.candidates.any { it.layer == layer }) {
                    effective[row.itemId]?.put(tagName, cell.value)
                    effective[row.itemId]?.put(cell.frame, cell.value)
                }
            }
        }
    }

    return Preview(rowsById.values.toList(), writeTags, files.size, scanErrors)
}
