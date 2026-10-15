package com.devxen.mp3csvtagger.engine

/**
 * Export tags to CSV — the reverse direction of a tagging run.
 *
 * One row per MP3, a "File" column with the file name, then one column per
 * tag name present in any file (in first-seen order, so a library's most
 * common tags land on the left). A tag a file does not have exports as an
 * empty cell. The result is a valid input CSV for this same app: set roles
 * on the columns, edit values in a spreadsheet, and run it back.
 */
fun exportTagsCsv(files: List<Mp3Item>): String {
    val tagNames = LinkedHashSet<String>()
    for (file in files) tagNames += file.tags.keys
    val header = listOf("File") + tagNames
    val rows = files.map { file ->
        listOf(file.displayName) + tagNames.map { name -> file.tags[name] ?: "" }
    }
    return CsvWriter.write(header, rows)
}

/**
 * The change log written with every Apply run. Format is the shared one:
 * file name `mp3tag_YYYYMMDD_HHMMSS.log.csv`, columns
 * Timestamp, File, Tag Name, ID3 Frame, Original/Old Value, New Value.
 * It is the human-readable companion to the tag-snapshot undo file that
 * sits next to it in the same run folder.
 */
object ChangeLog {
    val headers: List<String> =
        listOf("Timestamp", "File", "Tag Name", "ID3 Frame", "Original/Old Value", "New Value")

    /** One log row for a single tag write. */
    fun row(timestamp: String, file: String, tagName: String, frame: String, oldValue: String, newValue: String): List<String> =
        listOf(timestamp, file, tagName, frame, oldValue, newValue)
}
