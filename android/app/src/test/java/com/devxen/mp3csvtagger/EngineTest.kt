package com.devxen.mp3csvtagger

import com.devxen.mp3csvtagger.engine.CsvLayer
import com.devxen.mp3csvtagger.engine.CsvParser
import com.devxen.mp3csvtagger.engine.CsvSource
import com.devxen.mp3csvtagger.engine.FilenamePatternSource
import com.devxen.mp3csvtagger.engine.Matching
import com.devxen.mp3csvtagger.engine.Mp3Item
import com.devxen.mp3csvtagger.engine.Role
import com.devxen.mp3csvtagger.engine.TagNames
import com.devxen.mp3csvtagger.engine.buildPreview
import com.devxen.mp3csvtagger.engine.exportTagsCsv
import com.devxen.mp3csvtagger.engine.matchFilenamePattern
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Engine tests. The layered-CSV and multiple-candidate cases are the same
 * scenarios the desktop test-suite pins, run here against the Kotlin port —
 * the two engines must agree, because they share a format.
 */
class EngineTest {

    private fun layer(id: String, csvText: String, roles: Map<String, Role>): CsvLayer {
        val (headings, rows) = CsvParser.parse(csvText)
        val layer = CsvLayer(id, "$id.csv", headings, rows)
        for (tag in layer.tags) roles[tag.name]?.let { tag.role = it }
        return layer
    }

    private val rage = Mp3Item(
        "song1", "01 Township Rebellion.mp3",
        mapOf("TIT2" to "Township Rebellion", "TPE1" to "Rage Against the Machine", "TCON" to "Rock"),
    )
    private val other = Mp3Item(
        "song2", "02 Other Band.mp3",
        mapOf("TIT2" to "Something Else", "TPE1" to "Another Band", "TCON" to "Jazz"),
    )

    @Test
    fun normalizeMatchesSharedRule() {
        assertEquals(Matching.normalize("Rage Against the Machine"), Matching.normalize("rage against the machine!"))
        assertEquals(Matching.normalize("Don't Stop!"), Matching.normalize("dont stop"))
        assertEquals("", Matching.normalize(null))
    }

    @Test
    fun frameResolution() {
        assertEquals("TIT2", TagNames.frameForTagName("TIT2"))
        assertEquals("TIT2", TagNames.frameForTagName("Title"))
        assertEquals("TPE1", TagNames.frameForTagName("Lead Performer"))
        assertEquals("TPE1", TagNames.frameForTagName("Artist"))
        assertEquals("TXXX", TagNames.frameForTagName("Subgenre"))
    }

    @Test
    fun csvParserHandlesQuotingAndBlankRows() {
        val (headings, rows) = CsvParser.parse(
            "Title,Comment\n\"Hello, World\",\"He said \"\"hi\"\"\"\n\nShort\n"
        )
        assertEquals(listOf("Title", "Comment"), headings)
        assertEquals(2, rows.size) // blank row skipped, short row kept
        assertEquals("Hello, World", rows[0].values[0])
        assertEquals("He said \"hi\"", rows[0].values[1])
        assertEquals(listOf("Short", ""), rows[1].values) // padded
        assertEquals(1, rows[0].index)
    }

    @Test
    fun layeredPreviewMatchesDesktopBehaviour() {
        val sample1 = layer(
            "s1",
            "Lead Performer,Genre,Subgenre\nRage Against the Machine,Rap Metal,Political Rap Metal\n",
            mapOf("Lead Performer" to Role.Match, "Genre" to Role.Write, "Subgenre" to Role.Write),
        )
        val sample2 = layer(
            "s2",
            "Genre,Rating\nRap Metal,5\n",
            mapOf("Genre" to Role.Match, "Rating" to Role.Write),
        )
        val preview = buildPreview(listOf(CsvSource(sample1), CsvSource(sample2)), listOf(rage, other))
        assertEquals(2, preview.filesScanned)
        assertEquals(1, preview.filesMatched)
        val row = preview.rowForItem("song1")!!
        assertEquals("Rock", row.cells.getValue("Genre").oldValue)
        assertEquals("Rap Metal", row.cells.getValue("Genre").value)
        // Sample2 matched on the Genre that Sample1 writes (layering).
        assertEquals("5", row.cells.getValue("Rating").value)
        assertEquals("TXXX", row.cells.getValue("Rating").frame)
        assertNull(preview.rowForItem("song2"))
    }

    @Test
    fun multipleCandidatesLastLayerWinsAndCanBeReselected() {
        val first = layer("a", "Lead Performer,Genre\nRage Against the Machine,Metal\n",
            mapOf("Lead Performer" to Role.Match, "Genre" to Role.Write))
        val second = layer("b", "Lead Performer,Genre\nRage Against the Machine,Rap Metal\n",
            mapOf("Lead Performer" to Role.Match, "Genre" to Role.Write))
        val preview = buildPreview(listOf(CsvSource(first), CsvSource(second)), listOf(rage, other))
        val cell = preview.rowForItem("song1")!!.cells.getValue("Genre")
        assertTrue(cell.hasMultiple)
        assertEquals("Rap Metal", cell.value)
        cell.selected = 0
        assertEquals("Metal", cell.value)
    }

    @Test
    fun excludedLayerAndSkipColumnsDoNothing() {
        val layer = layer("a", "Lead Performer,Genre\nRage Against the Machine,Metal\n",
            mapOf("Lead Performer" to Role.Match, "Genre" to Role.Skip))
        layer.included = false
        val preview = buildPreview(listOf(CsvSource(layer)), listOf(rage))
        assertEquals(0, preview.filesMatched)
    }

    @Test
    fun filenamePatternCaptures() {
        val captures = matchFilenamePattern(
            "{Artist}/{Album}/{Track} - {Title}",
            "Rage Against the Machine/Rage Against the Machine/09 - Township Rebellion.mp3",
        )!!
        assertEquals("Rage Against the Machine", captures["Artist"])
        assertEquals("09", captures["Track"])
        assertEquals("Township Rebellion", captures["Title"])
        // Pattern anchors to the end of a deeper path.
        val deep = matchFilenamePattern("{Album}/{Title}", "Music/Rock/Greatest Hits/Anthem.mp3")!!
        assertEquals("Greatest Hits", deep["Album"])
        assertEquals("Anthem", deep["Title"])
        // Literal mismatch -> no match.
        assertNull(matchFilenamePattern("{Artist} - Live/{Title}", "Studio/Anthem.mp3"))
    }

    @Test
    fun filenamePatternLayerWritesIntoPreview() {
        val preview = buildPreview(
            listOf(FilenamePatternSource("{Artist} - {Title}")),
            listOf(Mp3Item("x", "Someone - A Song.mp3", emptyMap())),
        )
        val row = preview.rowForItem("x")!!
        assertEquals("Someone", row.cells.getValue("Artist").value)
        assertEquals("TPE1", row.cells.getValue("Artist").frame)
        assertEquals("A Song", row.cells.getValue("Title").value)
    }

    @Test
    fun exportProducesRoundTrippableCsv() {
        val csv = exportTagsCsv(listOf(rage, other))
        val (headings, rows) = CsvParser.parse(csv)
        assertEquals("File", headings.first())
        assertTrue("TCON" in headings)
        assertEquals("Township Rebellion", rows[0].values[headings.indexOf("TIT2")])
    }
}
