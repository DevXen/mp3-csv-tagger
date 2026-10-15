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
 * A [FilenamePatternLayer] can sit in the same layer list: instead of CSV
 * rows it derives each file's values from its own folder/file name, matched
 * per-file by construction.
 */

/** One value a CSV row (or pattern) wants to write, and where it came from. */
data class Candidate(
    val value: String,
    val sourceName: String,
    val sourceRow: Int,
    val layer: Int,
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

/** A layer in the stack: either a CSV file or a filename-pattern source. */
sealed interface LayerSource {
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
            Cell(tagName, frame, item.valueFor(tagName, frame))
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
