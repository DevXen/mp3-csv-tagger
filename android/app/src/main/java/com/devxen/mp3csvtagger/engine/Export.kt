package com.devxen.mp3csvtagger.engine

/**
 * Export tags to CSV — the reverse direction of a tagging run.
 *
 * One row per MP3: a "File" column with the file name, a "FilePath"
 * column with the file's path relative to the picked folder (the SAF
 * display path, e.g. "Artist/Album/01 Song.mp3"), then one column per
 * tag name present in any file (in first-seen order, so a library's
 * most common tags land on the left). A tag a file does not have
 * exports as an empty cell. The result is a valid input CSV for this
 * same app: set roles on the columns, edit values in a spreadsheet,
 * and run it back.
 *
 * Exports can also *append*: [appendTagsCsv] merges a fresh scan into
 * an existing export CSV instead of replacing it, so a library CSV
 * can be built up folder by folder (see that function's doc).
 */

/** The file-name column every export starts with. */
const val FILE_COLUMN = "File"

/** The path column (relative to the picked folder) exports carry. */
const val FILE_PATH_COLUMN = "FilePath"

/**
 * The columns a fresh export of [files] produces: "File", "FilePath",
 * then the union of tag names in first-seen order.
 */
fun exportColumns(files: List<Mp3Item>): List<String> {
    val tagNames = LinkedHashSet<String>()
    for (file in files) tagNames += file.tags.keys
    return listOf(FILE_COLUMN, FILE_PATH_COLUMN) + tagNames
}

/**
 * One export row for [file] as a column-to-value map. [filePaths]
 * maps an item id to its path relative to the picked folder; an item
 * with no entry falls back to its display name (the path IS the name
 * for a file at the folder root as far as a bare engine test knows).
 */
fun exportRow(file: Mp3Item, filePaths: Map<String, String>): Map<String, String> {
    val row = LinkedHashMap<String, String>()
    row[FILE_COLUMN] = file.displayName
    row[FILE_PATH_COLUMN] = filePaths[file.id] ?: file.displayName
    for ((name, value) in file.tags) row[name] = value
    return row
}

/** Render a fresh export of [files] as CSV text. */
fun exportTagsCsv(files: List<Mp3Item>, filePaths: Map<String, String> = emptyMap()): String {
    val header = exportColumns(files)
    val rows = files.map { file ->
        val row = exportRow(file, filePaths)
        header.map { column -> row[column] ?: "" }
    }
    return CsvWriter.write(header, rows)
}

/** Outcome of one [appendTagsCsv] merge. */
data class AppendSummary(
    /** How many files the new scan covered. */
    val filesScanned: Int,
    /** Scan files that had no row yet; appended at the end. */
    val rowsAdded: Int,
    /** Existing rows refreshed in place because their file was scanned. */
    val rowsUpdated: Int,
    /** Existing rows left untouched (their file was not in this scan). */
    val rowsKept: Int,
    /** Tag columns the scan introduced, appended to the header. */
    val columnsAdded: List<String>,
    /** The column rows were matched on: "FilePath", or "File" as fallback. */
    val keyColumn: String,
    /** A caution about the merge (set when the fallback key was used). */
    val warning: String?,
)

/** The merged CSV text plus the [AppendSummary] describing the merge. */
data class AppendResult(val csvText: String, val summary: AppendSummary)

/**
 * Merge a fresh scan into an existing export CSV, mirroring the
 * desktop program's append export rule for rule:
 *
 * - Columns: the existing header order is preserved; tag columns the
 *   scan produces that the CSV lacks are appended at the end (blank
 *   for rows that were already there).
 * - Rows are keyed by the "FilePath" column. An existing row whose
 *   file is in the scan is updated in place — same position, fresh
 *   values — but only for the columns this scan produces: a column
 *   the scan does not produce (say a hand-written note column) is
 *   never erased by the merge. Rows whose files are not in the scan
 *   are kept untouched, in place. New files append at the end, in
 *   scan order.
 * - If the existing CSV has no "FilePath" column (an export from
 *   before that column existed, or one trimmed in a spreadsheet),
 *   rows fall back to keying on the "File" name column and the
 *   summary's warning says so: names are weaker keys than paths,
 *   because two different files can share a name.
 *
 * @throws IllegalArgumentException if the existing text has no
 * header row, or has neither a "FilePath" nor a "File" column to
 * key rows on.
 */
fun appendTagsCsv(
    existingText: String,
    files: List<Mp3Item>,
    filePaths: Map<String, String> = emptyMap(),
): AppendResult {
    val (headings, existingRows) = CsvParser.parse(existingText)
    require(headings.isNotEmpty()) { "That CSV has no header row, so there is nothing to append into." }

    val keyColumn: String
    val warning: String?
    when {
        FILE_PATH_COLUMN in headings -> {
            keyColumn = FILE_PATH_COLUMN
            warning = null
        }
        FILE_COLUMN in headings -> {
            keyColumn = FILE_COLUMN
            warning = "That CSV has no FilePath column, so rows were matched by file name only. " +
                "Different files that share a name would be treated as the same file — " +
                "re-export with FilePath when you can."
        }
        else -> throw IllegalArgumentException(
            "That CSV has neither a FilePath nor a File column to match rows on."
        )
    }

    // Columns the scan introduces go at the end of the existing order.
    val scanColumns = exportColumns(files)
    val mergedColumns = headings.toMutableList()
    val columnsAdded = mutableListOf<String>()
    for (column in scanColumns) {
        if (column !in mergedColumns) {
            mergedColumns += column
            columnsAdded += column
        }
    }

    val scanRows = files.map { exportRow(it, filePaths) }
    // Index the scan by key value; first row wins if a scan somehow
    // holds the same file twice, so the merge stays deterministic.
    val scanByKey = LinkedHashMap<String, Map<String, String>>()
    for (row in scanRows) scanByKey.putIfAbsent(row.getValue(keyColumn), row)

    var rowsUpdated = 0
    var rowsKept = 0
    val mergedRows = mutableListOf<Map<String, String>>()
    for (indexed in existingRows) {
        val existing = headings.zip(indexed.values).toMap()
        val key = existing[keyColumn] ?: ""
        // remove() consumes the scan row: a duplicated row in the
        // existing CSV for the same file is kept, not double-updated.
        val fresh = if (key.isEmpty()) null else scanByKey.remove(key)
        if (fresh == null) {
            rowsKept++
            mergedRows += existing
        } else {
            // Refresh only the columns this scan produces; every
            // other column keeps the value already in the CSV.
            val updated = LinkedHashMap(existing)
            for (column in scanColumns) updated[column] = fresh[column] ?: ""
            rowsUpdated++
            mergedRows += updated
        }
    }

    // Whatever is left in the scan is new to this CSV: append at the
    // end, in scan order, each key once.
    var rowsAdded = 0
    for (row in scanRows) {
        val key = row.getValue(keyColumn)
        if (key in scanByKey) {
            mergedRows += row
            rowsAdded++
            scanByKey.remove(key)
        }
    }

    val sequences = mergedRows.map { row -> mergedColumns.map { column -> row[column] ?: "" } }
    return AppendResult(
        csvText = CsvWriter.write(mergedColumns, sequences),
        summary = AppendSummary(
            filesScanned = files.size,
            rowsAdded = rowsAdded,
            rowsUpdated = rowsUpdated,
            rowsKept = rowsKept,
            columnsAdded = columnsAdded,
            keyColumn = keyColumn,
            warning = warning,
        ),
    )
}

/**
 * The change log written with every Apply run. Format is the shared one:
 * file name `mp3tag_YYYYMMDD_HHMMSS.log.csv`, columns
 * Timestamp, File, Tag Name, ID3 Frame, Original/Old Value, New Value, Source.
 * The trailing Source column (round 2, matching the desktop log) records
 * the selected candidate's source name for each write — a CSV file name,
 * "tag sync", a filename pattern, or "manual edit" for a hand-typed value.
 * It is the human-readable companion to the tag-snapshot undo file that
 * sits next to it in the same run folder.
 */
object ChangeLog {
    val headers: List<String> =
        listOf("Timestamp", "File", "Tag Name", "ID3 Frame", "Original/Old Value", "New Value", "Source")

    /** One log row for a single tag write. */
    fun row(
        timestamp: String, file: String, tagName: String, frame: String,
        oldValue: String, newValue: String, source: String,
    ): List<String> =
        listOf(timestamp, file, tagName, frame, oldValue, newValue, source)
}
