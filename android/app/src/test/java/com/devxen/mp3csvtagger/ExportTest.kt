package com.devxen.mp3csvtagger

import com.devxen.mp3csvtagger.engine.ChangeLog
import com.devxen.mp3csvtagger.engine.CsvParser
import com.devxen.mp3csvtagger.engine.CsvWriter
import com.devxen.mp3csvtagger.engine.Mp3Item
import com.devxen.mp3csvtagger.engine.appendTagsCsv
import com.devxen.mp3csvtagger.engine.exportTagsCsv
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Append (merge) library export — building one library CSV up folder
 * by folder. Mirrors the desktop test cases for the same feature:
 * existing column order is preserved with new columns last, rows are
 * keyed by FilePath (File name fallback, with a warning), a
 * re-scanned file's row updates in place and never duplicates, rows
 * outside the scan are kept untouched, and a column the scan does not
 * produce never loses its values.
 */
class ExportTest {

    // Item ids double as their FilePath values in these fixtures: the
    // engine keys rows on the path map, and using the path as the id
    // keeps the fixtures one line per file.
    private fun item(path: String, vararg tags: Pair<String, String>) =
        Mp3Item(path, path.substringAfterLast('/'), linkedMapOf(*tags))

    private fun pathsOf(files: List<Mp3Item>): Map<String, String> =
        files.associate { it.id to it.id }

    private fun folderA() = listOf(
        item("a/one.mp3", "TIT2" to "One", "TPE1" to "Artist A", "TCON" to "Rock"),
        item("a/two.mp3", "TIT2" to "Two", "TPE1" to "Artist A", "TCON" to "Rock"),
    )

    private fun folderB() = listOf(
        item("b/three.mp3", "TIT2" to "Three", "TPE1" to "Artist B", "TDRC" to "1999"),
        item("b/four.mp3", "TIT2" to "Four", "TPE1" to "Artist B"),
    )

    private fun rowsByPath(csv: String): Pair<List<String>, Map<String, Map<String, String>>> {
        val (headings, rows) = CsvParser.parse(csv)
        val byPath = LinkedHashMap<String, Map<String, String>>()
        for (row in rows) {
            val cells = headings.zip(row.values).toMap()
            byPath[cells.getValue("FilePath")] = cells
        }
        return headings to byPath
    }

    private fun rowOrder(csv: String): List<String> {
        val (headings, rows) = CsvParser.parse(csv)
        return rows.map { it.values[headings.indexOf("FilePath")] }
    }

    @Test
    fun exportCarriesFilePathColumn() {
        val files = folderA()
        val (headings, byPath) = rowsByPath(exportTagsCsv(files, pathsOf(files)))
        assertEquals(listOf("File", "FilePath", "TIT2", "TPE1", "TCON"), headings)
        assertEquals("one.mp3", byPath.getValue("a/one.mp3")["File"])
        assertEquals("a/one.mp3", byPath.getValue("a/one.mp3")["FilePath"])
    }

    @Test
    fun appendSecondFolderUnionsRowsAndColumns() {
        val filesA = folderA()
        val existing = exportTagsCsv(filesA, pathsOf(filesA))
        val filesB = folderB()

        val result = appendTagsCsv(existing, filesB, pathsOf(filesB))

        assertEquals(2, result.summary.filesScanned)
        assertEquals(2, result.summary.rowsAdded)
        assertEquals(0, result.summary.rowsUpdated)
        assertEquals(2, result.summary.rowsKept)
        assertEquals("FilePath", result.summary.keyColumn)
        assertNull(result.summary.warning)
        assertEquals(listOf("TDRC"), result.summary.columnsAdded)

        val (headings, byPath) = rowsByPath(result.csvText)
        // Existing column order preserved, TDRC appended at the end.
        assertEquals(listOf("File", "FilePath", "TIT2", "TPE1", "TCON", "TDRC"), headings)
        assertEquals(4, byPath.size)
        // Folder A rows kept their position; folder B rows appended after.
        assertEquals(
            listOf("a/one.mp3", "a/two.mp3", "b/three.mp3", "b/four.mp3"),
            rowOrder(result.csvText),
        )
        assertEquals("", byPath.getValue("a/one.mp3")["TDRC"])
        assertEquals("1999", byPath.getValue("b/three.mp3")["TDRC"])
        assertEquals("", byPath.getValue("b/three.mp3")["TCON"])
    }

    @Test
    fun appendRescanUpdatesRowsInPlaceWithoutDuplicates() {
        val filesA = folderA()
        var csv = exportTagsCsv(filesA, pathsOf(filesA))
        csv = appendTagsCsv(csv, folderB(), pathsOf(folderB())).csvText

        val changed = listOf(
            item("a/one.mp3", "TIT2" to "One", "TPE1" to "Artist A", "TCON" to "Metal"),
            folderA()[1],
        )
        val result = appendTagsCsv(csv, changed, pathsOf(changed))

        assertEquals(2, result.summary.rowsUpdated)
        assertEquals(0, result.summary.rowsAdded)
        assertEquals(2, result.summary.rowsKept)
        val (_, byPath) = rowsByPath(result.csvText)
        assertEquals(4, byPath.size) // no duplicates
        assertEquals(
            listOf("a/one.mp3", "a/two.mp3", "b/three.mp3", "b/four.mp3"),
            rowOrder(result.csvText),
        )
        assertEquals("Metal", byPath.getValue("a/one.mp3")["TCON"])
        assertEquals("Three", byPath.getValue("b/three.mp3")["TIT2"])
    }

    @Test
    fun appendPreservesUnrelatedRowsAndColumns() {
        val existing = CsvWriter.write(
            listOf("File", "FilePath", "TIT2", "Comment"),
            listOf(
                listOf("one.mp3", "a/one.mp3", "One", "keep me"),
                listOf("other.mp3", "elsewhere/other.mp3", "Other", "untouched"),
            ),
        )
        val filesA = folderA()
        val result = appendTagsCsv(existing, filesA, pathsOf(filesA))

        assertEquals(1, result.summary.rowsUpdated)
        assertEquals(1, result.summary.rowsKept)
        assertEquals(1, result.summary.rowsAdded)
        val (_, byPath) = rowsByPath(result.csvText)
        // The scan produces no Comment column, so the hand-written
        // value survives the refresh of one.mp3's row.
        assertEquals("keep me", byPath.getValue("a/one.mp3")["Comment"])
        assertEquals("Rock", byPath.getValue("a/one.mp3")["TCON"])
        assertEquals("untouched", byPath.getValue("elsewhere/other.mp3")["Comment"])
        assertEquals("", byPath.getValue("elsewhere/other.mp3")["TCON"])
    }

    @Test
    fun appendFallsBackToFileNameKeyWithWarning() {
        // A CSV trimmed in a spreadsheet: the FilePath column is gone.
        val existing = CsvWriter.write(
            listOf("File", "TIT2", "TPE1"),
            listOf(
                listOf("one.mp3", "One", "Artist A"),
                listOf("gone.mp3", "Gone", "Nobody"),
            ),
        )
        val filesA = folderA()
        val result = appendTagsCsv(existing, filesA, pathsOf(filesA))

        assertEquals("File", result.summary.keyColumn)
        assertNotNull(result.summary.warning)
        assertTrue(result.summary.warning!!.contains("FilePath"))
        assertEquals(1, result.summary.rowsUpdated)
        assertEquals(1, result.summary.rowsAdded)
        assertEquals(1, result.summary.rowsKept)
        val (_, rows) = CsvParser.parse(result.csvText)
        assertEquals(3, rows.size)
    }

    @Test
    fun changeLogHasTrailingSourceColumn() {
        // Round 2 parity with the desktop log: the existing columns keep
        // their order and positions, and "Source" (the selected
        // candidate's source name — "manual edit" for hand edits) is
        // appended last.
        assertEquals(
            listOf(
                "Timestamp", "File", "Tag Name", "ID3 Frame",
                "Original/Old Value", "New Value", "Source",
            ),
            ChangeLog.headers,
        )
        assertEquals(
            listOf("2026/01/01 00:00:00", "one.mp3", "Genre", "TCON", "Rock", "Metal", "manual edit"),
            ChangeLog.row(
                "2026/01/01 00:00:00", "one.mp3", "Genre", "TCON", "Rock", "Metal", "manual edit",
            ),
        )
    }

    @Test
    fun appendRejectsHeaderlessAndKeylessCsv() {
        assertThrows(IllegalArgumentException::class.java) {
            appendTagsCsv("", folderA(), pathsOf(folderA()))
        }
        val keyless = CsvWriter.write(
            listOf("TIT2", "TPE1"),
            listOf(listOf("One", "Artist A")),
        )
        assertThrows(IllegalArgumentException::class.java) {
            appendTagsCsv(keyless, folderA(), pathsOf(folderA()))
        }
    }
}
