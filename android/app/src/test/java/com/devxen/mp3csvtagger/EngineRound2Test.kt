package com.devxen.mp3csvtagger

import com.devxen.mp3csvtagger.engine.COVER_PRESENT
import com.devxen.mp3csvtagger.engine.COVER_TAG_NAME
import com.devxen.mp3csvtagger.engine.COVER_TOKEN_PREFIX
import com.devxen.mp3csvtagger.engine.Cell
import com.devxen.mp3csvtagger.engine.CompletenessData
import com.devxen.mp3csvtagger.engine.CsvLayer
import com.devxen.mp3csvtagger.engine.CsvParser
import com.devxen.mp3csvtagger.engine.CsvSource
import com.devxen.mp3csvtagger.engine.Job
import com.devxen.mp3csvtagger.engine.JobCsvLayer
import com.devxen.mp3csvtagger.engine.JobPatternLayer
import com.devxen.mp3csvtagger.engine.MANUAL_LAYER
import com.devxen.mp3csvtagger.engine.MANUAL_SOURCE
import com.devxen.mp3csvtagger.engine.Mp3Item
import com.devxen.mp3csvtagger.engine.NO_ALBUM
import com.devxen.mp3csvtagger.engine.Role
import com.devxen.mp3csvtagger.engine.SYNC_SOURCE_NAME
import com.devxen.mp3csvtagger.engine.TagNames
import com.devxen.mp3csvtagger.engine.ValuesSource
import com.devxen.mp3csvtagger.engine.albumCompleteness
import com.devxen.mp3csvtagger.engine.buildPreview
import com.devxen.mp3csvtagger.engine.buildSyncValues
import com.devxen.mp3csvtagger.engine.checkConsistency
import com.devxen.mp3csvtagger.engine.coverToken
import com.devxen.mp3csvtagger.engine.coverTokenSourceId
import com.devxen.mp3csvtagger.engine.defaultSyncTags
import com.devxen.mp3csvtagger.engine.duplicateGroups
import com.devxen.mp3csvtagger.engine.pairLibraries
import com.devxen.mp3csvtagger.engine.relativeKey
import com.devxen.mp3csvtagger.engine.renderCompletenessText
import com.devxen.mp3csvtagger.engine.tagDifferences
import com.devxen.mp3csvtagger.engine.variantGroups
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Round-2 engine tests: manual preview edits, virtual value layers,
 * two-library tag sync, tags-vs-path consistency, album completeness
 * (plus duplicates/variants) and saved jobs. These are the same
 * scenarios the desktop round-2 suite pins, run against the Kotlin
 * port — the two engines must agree, because they share the rules.
 */
class EngineRound2Test {

    private fun layer(id: String, csvText: String, roles: Map<String, Role>): CsvLayer {
        val (headings, rows) = CsvParser.parse(csvText)
        val layer = CsvLayer(id, "$id.csv", headings, rows)
        for (tag in layer.tags) roles[tag.name]?.let { tag.role = it }
        return layer
    }

    private fun item(id: String, vararg tags: Pair<String, String>) =
        Mp3Item(id, id.substringAfterLast('/'), linkedMapOf(*tags))

    // ------------------------------------------------------------------
    // Manual edits
    // ------------------------------------------------------------------

    @Test
    fun manualEditOverridesLayeredCandidate() {
        val csv = layer(
            "a", "Lead Performer,Genre\nRage Against the Machine,Rap Metal\n",
            mapOf("Lead Performer" to Role.Match, "Genre" to Role.Write),
        )
        val rage = item("song1", "TPE1" to "Rage Against the Machine", "TCON" to "Rock")
        val preview = buildPreview(listOf(CsvSource(csv)), listOf(rage))
        val cell = preview.rowForItem("song1")!!.cells.getValue("Genre")
        assertEquals("Rap Metal", cell.value)
        assertNull(cell.manualCandidate)

        cell.setManualEdit("Hand Typed")

        assertEquals("Hand Typed", cell.value)
        val manual = cell.manualCandidate!!
        assertTrue(manual.manual)
        assertEquals(MANUAL_SOURCE, manual.sourceName)
        assertEquals("manual edit", manual.sourceName)
        assertEquals(MANUAL_LAYER, manual.layer)
        assertEquals(1_000_000, manual.layer)
        assertEquals(-1, manual.sourceRow)
        // The layered candidate is untouched underneath the edit.
        assertEquals(2, cell.candidates.size)
        assertEquals("Rap Metal", cell.candidates[0].value)
        assertFalse(cell.candidates[0].manual)
    }

    @Test
    fun manualEditReplacesPreviousManualEdit() {
        val cell = Cell("Genre", "TCON", "Rock")
        cell.setManualEdit("First")
        cell.setManualEdit("Second")
        assertEquals(1, cell.candidates.size)
        assertEquals("Second", cell.value)
        assertEquals("Second", cell.manualCandidate!!.value)
    }

    @Test
    fun clearManualEditRevertsToLayeredValue() {
        val csv = layer(
            "a", "Lead Performer,Genre\nRage Against the Machine,Rap Metal\n",
            mapOf("Lead Performer" to Role.Match, "Genre" to Role.Write),
        )
        val rage = item("song1", "TPE1" to "Rage Against the Machine", "TCON" to "Rock")
        val cell = buildPreview(listOf(CsvSource(csv)), listOf(rage))
            .rowForItem("song1")!!.cells.getValue("Genre")
        cell.setManualEdit("Hand Typed")
        cell.clearManualEdit()
        assertNull(cell.manualCandidate)
        assertEquals("Rap Metal", cell.value)
        // Clearing again (no manual candidate) is a no-op.
        cell.clearManualEdit()
        assertEquals("Rap Metal", cell.value)
        assertEquals(1, cell.candidates.size)
    }

    @Test
    fun manualEditOnCellWithoutCandidates() {
        val cell = Cell("Genre", "TCON", "Rock")
        cell.setManualEdit("Metal")
        assertEquals("Metal", cell.value)
        assertTrue(cell.changed)
        cell.clearManualEdit()
        assertTrue(cell.candidates.isEmpty())
        assertEquals("Rock", cell.value) // back to the stored value
        assertFalse(cell.changed)
    }

    // ------------------------------------------------------------------
    // Virtual value layers (ValuesSource)
    // ------------------------------------------------------------------

    @Test
    fun valuesSourceFeedsPreviewLikeAnyLayer() {
        val rage = item("song1", "TPE1" to "Rage Against the Machine", "TCON" to "Rock")
        val other = item("song2", "TPE1" to "Another Band")
        val source = ValuesSource(
            "tag sync",
            mapOf(
                "song1" to mapOf("Genre" to "Rap Metal", "Rating" to "5"),
                "missing-id" to mapOf("Genre" to "Ghost"),
            ),
        )
        val preview = buildPreview(listOf(source), listOf(rage, other))
        // Only the scanned file appears; the stale id invents no row.
        assertEquals(1, preview.filesMatched)
        val row = preview.rowForItem("song1")!!
        val genre = row.cells.getValue("Genre")
        assertEquals("Rock", genre.oldValue)
        assertEquals("Rap Metal", genre.value)
        assertEquals("tag sync", genre.candidates.single().sourceName)
        assertEquals("TXXX", row.cells.getValue("Rating").frame)
        assertEquals(listOf("Genre", "Rating"), preview.writeTags)
        assertEquals(2, preview.totalChanges)
    }

    @Test
    fun valuesSourceLayersAfterCsvAndCanBeExcluded() {
        val csv = layer(
            "a", "Lead Performer,Genre\nRage Against the Machine,Metal\n",
            mapOf("Lead Performer" to Role.Match, "Genre" to Role.Write),
        )
        val rage = item("song1", "TPE1" to "Rage Against the Machine", "TCON" to "Rock")
        val values = ValuesSource(SYNC_SOURCE_NAME, mapOf("song1" to mapOf("Genre" to "Rap Metal")))
        val preview = buildPreview(listOf(CsvSource(csv), values), listOf(rage))
        val cell = preview.rowForItem("song1")!!.cells.getValue("Genre")
        assertTrue(cell.hasMultiple)
        assertEquals("Rap Metal", cell.value) // the later layer wins

        val excluded = ValuesSource("off", mapOf("song1" to mapOf("Genre" to "X")), included = false)
        assertEquals(0, buildPreview(listOf(excluded), listOf(rage)).filesMatched)
    }

    // ------------------------------------------------------------------
    // Sync
    // ------------------------------------------------------------------

    private fun sourceLibrary() = listOf(
        Mp3Item(
            "s1", "01 Song.mp3",
            mapOf("TIT2" to "Song", "TPE1" to "Rage", "TCON" to "Rock"),
            hasCover = true, coverKey = "aaa",
        ),
        Mp3Item(
            "s2", "02 Other.mp3",
            mapOf("TIT2" to "Other", "TPE1" to "Rage", "TCON" to ""),
        ),
        item("s3", "TIT2" to "Source Only"),
    )

    private fun targetLibrary() = listOf(
        Mp3Item(
            "t1", "01 Song.mp3",
            mapOf("TIT2" to "Song", "TPE1" to "Rage", "TCON" to "Jazz"),
            hasCover = true, coverKey = "bbb",
        ),
        item("t2", "TIT2" to "Other", "TPE1" to "", "TCON" to "Blues"),
        item("t3", "TIT2" to "Target Only"),
    )

    private fun sourcePaths() = mapOf(
        "s1" to "Rage/Album/01 Song.mp3",
        "s2" to "Rage/Album/02 Other.mp3",
        "s3" to "Solo/Only Source.mp3",
    )

    private fun targetPaths() = mapOf(
        // Deliberately different case: pairing is case-insensitive.
        "t1" to "rage/album/01 song.mp3",
        "t2" to "Rage/Album/02 Other.mp3",
        "t3" to "Extra/Only Target.mp3",
    )

    private fun plan() = pairLibraries(sourceLibrary(), targetLibrary(), sourcePaths(), targetPaths())

    @Test
    fun relativeKeyCasefoldsAndNormalisesSeparators() {
        assertEquals("artist/album/song.mp3", relativeKey("Artist\\Album/Song.mp3"))
        assertEquals(relativeKey("A/B.mp3"), relativeKey("a/b.mp3"))
    }

    @Test
    fun syncPairingByRelativePath() {
        val plan = plan()
        assertEquals(listOf("s1" to "t1", "s2" to "t2"), plan.pairs.map { it.sourceId to it.targetId })
        assertEquals("rage/album/01 song.mp3", plan.pairs[0].relKey)
        assertEquals(listOf("s3"), plan.unpairedSource)
        assertEquals(listOf("t3"), plan.unpairedTarget)
    }

    @Test
    fun syncPairingFirstTargetWinsOnCaseCollision() {
        val source = listOf(item("s", "TIT2" to "X"))
        val targets = listOf(item("ta", "TIT2" to "X"), item("tb", "TIT2" to "X"))
        val plan = pairLibraries(
            source, targets,
            mapOf("s" to "Album/Song.mp3"),
            mapOf("ta" to "Album/Song.mp3", "tb" to "album/song.mp3"),
        )
        assertEquals(listOf("ta"), plan.pairs.map { it.targetId })
        assertEquals(listOf("tb"), plan.unpairedTarget)
    }

    @Test
    fun defaultSyncTagsArePairedSourceTagsInOrder() {
        assertEquals(listOf("TIT2", "TPE1", "TCON"), defaultSyncTags(plan(), sourceLibrary()))
    }

    @Test
    fun syncDifferencesAndValuesAgree() {
        val tags = listOf("TIT2", "TPE1", "TCON")
        val differences = tagDifferences(plan(), sourceLibrary(), targetLibrary(), tags, includeCover = true)
        // Pair 1: Genre differs, cover differs. Pair 2: Artist differs.
        // Identical values and empty source values never appear.
        assertEquals(3, differences.size)
        val genre = differences.single { it.tag == "TCON" }
        assertEquals("t1", genre.targetId)
        assertEquals("Rock", genre.sourceValue)
        assertEquals("Jazz", genre.targetValue)
        val artist = differences.single { it.tag == "TPE1" }
        assertEquals("t2", artist.targetId)
        assertEquals("Rage", artist.sourceValue)
        assertEquals("", artist.targetValue)
        val cover = differences.single { it.tag == COVER_TAG_NAME }
        assertEquals(COVER_PRESENT, cover.sourceValue)
        assertEquals(COVER_PRESENT, cover.targetValue) // target has (different) art

        val values = buildSyncValues(plan(), sourceLibrary(), targetLibrary(), tags, includeCover = true)
        assertEquals(setOf("t1", "t2"), values.keys)
        assertEquals("Rock", values.getValue("t1")["TCON"])
        assertEquals("Rage", values.getValue("t2")["TPE1"])
        // The empty source Genre must not erase the target's "Blues".
        assertFalse(values.getValue("t2").containsKey("TCON"))
        // The cover entry is the opaque UI-resolved token, never bytes.
        val token = values.getValue("t1").getValue(COVER_TAG_NAME)
        assertTrue(token.startsWith(COVER_TOKEN_PREFIX))
        assertEquals("s1", coverTokenSourceId(token))
        assertNull(coverTokenSourceId("not a token"))
        assertEquals(token, coverToken(sourceLibrary()[0]))
    }

    @Test
    fun syncCoverNeedsProvableDifference() {
        fun pair(sourceCover: Mp3Item, targetCover: Mp3Item): Map<String, Map<String, String>> {
            val plan = pairLibraries(
                listOf(sourceCover), listOf(targetCover),
                mapOf(sourceCover.id to "A/Song.mp3"), mapOf(targetCover.id to "A/Song.mp3"),
            )
            return buildSyncValues(plan, listOf(sourceCover), listOf(targetCover), emptyList(), includeCover = true)
        }
        // Source has a cover, target has none: provable, token proposed
        // even though the source scan could not hash its cover.
        val noTargetCover = pair(
            Mp3Item("s", "Song.mp3", emptyMap(), hasCover = true, coverKey = null),
            Mp3Item("t", "Song.mp3", emptyMap(), hasCover = false),
        )
        assertEquals("cover:s", noTargetCover.getValue("t")[COVER_TAG_NAME])
        // Both have covers but a key is missing: NOT provable, no entry.
        val unknownKeys = pair(
            Mp3Item("s", "Song.mp3", emptyMap(), hasCover = true, coverKey = null),
            Mp3Item("t", "Song.mp3", emptyMap(), hasCover = true, coverKey = "bbb"),
        )
        assertTrue(unknownKeys.isEmpty())
        // Same key on both sides: same cover, no entry.
        val sameCover = pair(
            Mp3Item("s", "Song.mp3", emptyMap(), hasCover = true, coverKey = "same"),
            Mp3Item("t", "Song.mp3", emptyMap(), hasCover = true, coverKey = "same"),
        )
        assertTrue(sameCover.isEmpty())
        // Source has no cover: nothing to copy, whatever the target has.
        val noSourceCover = pair(
            Mp3Item("s", "Song.mp3", emptyMap(), hasCover = false),
            Mp3Item("t", "Song.mp3", emptyMap(), hasCover = true, coverKey = "bbb"),
        )
        assertTrue(noSourceCover.isEmpty())
        // includeCover = false suppresses the cover entry entirely.
        val plan = plan()
        val textOnly = buildSyncValues(plan, sourceLibrary(), targetLibrary(), listOf("TCON"), includeCover = false)
        assertFalse(textOnly.getValue("t1").containsKey(COVER_TAG_NAME))
    }

    @Test
    fun syncValuesFlowThroughPreviewAsTagSyncLayer() {
        val values = buildSyncValues(plan(), sourceLibrary(), targetLibrary(), listOf("TIT2", "TPE1", "TCON"), includeCover = true)
        val preview = buildPreview(
            listOf(ValuesSource(SYNC_SOURCE_NAME, values)),
            targetLibrary(),
        )
        assertEquals(2, preview.filesMatched) // t3 (unpaired) never appears
        assertNull(preview.rowForItem("t3"))
        val row = preview.rowForItem("t1")!!
        val genre = row.cells.getValue("TCON")
        assertEquals("Jazz", genre.oldValue)
        assertEquals("Rock", genre.value)
        assertEquals(SYNC_SOURCE_NAME, genre.candidates.single().sourceName)
        // The cover cell: APIC frame, old value is the presence marker.
        val cover = row.cells.getValue(COVER_TAG_NAME)
        assertEquals("APIC", cover.frame)
        assertEquals(COVER_PRESENT, cover.oldValue)
        assertTrue(cover.changed)
        assertEquals("APIC", TagNames.frameForTagName("Cover Art"))
    }

    // ------------------------------------------------------------------
    // Consistency
    // ------------------------------------------------------------------

    @Test
    fun consistencyFindsMismatchesAndUnmatched() {
        val pattern = "{Artist}/{Album}/{Track} - {Title}"
        val files = listOf(
            item("c1", "TPE1" to "Rage Against the Machine", "TALB" to "Rage Against the Machine", "TRCK" to "09", "TIT2" to "Township Rebellion"),
            item("c2", "TPE1" to "rage against the machine!", "TALB" to "Rage Against the Machine", "TRCK" to "09", "TIT2" to "Wrong Title"),
            item("c3", "TIT2" to "Anything"),
            item("c4", "TPE1" to "Rage Against the Machine", "TALB" to "Rage Against the Machine", "TRCK" to "01"),
        )
        val paths = mapOf(
            "c1" to "Rage Against the Machine/Rage Against the Machine/09 - Township Rebellion.mp3",
            "c2" to "Rage Against the Machine/Rage Against the Machine/09 - Township Rebellion.mp3",
            "c3" to "random.mp3",
            "c4" to "Rage Against the Machine/Rage Against the Machine/01 - Ghost.mp3",
        )
        val result = checkConsistency(files, paths, pattern)
        assertEquals(4, result.filesChecked)
        assertEquals(3, result.checked)
        assertEquals(listOf("c3"), result.unmatched)
        // c1 agrees. c2's artist differs only in case/punctuation (not a
        // mismatch) but its Title is wrong. c4's path names a Title the
        // file does not carry at all.
        assertEquals(2, result.mismatches.size)
        val title = result.mismatches.single { it.itemId == "c2" }
        assertEquals("Title", title.tag)
        assertEquals("Township Rebellion", title.pathValue)
        assertEquals("Wrong Title", title.tagValue)
        val ghost = result.mismatches.single { it.itemId == "c4" }
        assertEquals("Ghost", ghost.pathValue)
        assertEquals("", ghost.tagValue)
    }

    @Test
    fun consistencyModuleIsStructurallyReadOnly() {
        // The desktop module pins its read-only guarantee by scanning
        // its own imports; the equivalent pin here: Consistency.kt must
        // not reference the tagio package (the only code that can write
        // or read file bytes) at all.
        val candidates = listOf(
            File("src/main/java/com/devxen/mp3csvtagger/engine/Consistency.kt"),
            File("app/src/main/java/com/devxen/mp3csvtagger/engine/Consistency.kt"),
        )
        val source = candidates.firstOrNull { it.isFile }?.readText()
        assertTrue("Consistency.kt not found from ${File(".").absolutePath}", source != null)
        // Imports are the structural guarantee (the file's doc comment
        // may *mention* the tagio package; it must never import it, nor
        // name the writer/reader classes anywhere).
        val imports = source!!.lines().filter { it.trimStart().startsWith("import") }
        assertTrue(imports.none { it.contains("tagio") })
        assertFalse(source.contains("JauTagIO"))
        assertFalse(source.contains("Id3Reader"))
    }

    // ------------------------------------------------------------------
    // Completeness, duplicates, variants
    // ------------------------------------------------------------------

    private fun abbeyRoad() = listOf(
        Mp3Item(
            "f1", "01 Come Together.mp3",
            mapOf("TIT2" to "Come Together", "TPE1" to "The Beatles", "TALB" to "Abbey Road", "TYER" to "1969", "TCON" to "Rock", "TRCK" to "1"),
            hasCover = true,
        ),
        // Year arrives as TDRC here: it still counts (desktop rule).
        item("f2", "TIT2" to "Something", "TPE1" to "The Beatles", "TALB" to "Abbey Road", "TDRC" to "1969"),
        item("f3", "TIT2" to "Orphan"),
    )

    @Test
    fun albumCompletenessCountsAndPercents() {
        val data: CompletenessData = albumCompleteness(abbeyRoad())
        assertEquals(3, data.summaryFiles)
        assertEquals(2, data.summaryAlbums)

        val abbey = data.albums.single { it.album == "Abbey Road" }
        assertEquals("The Beatles", abbey.artist)
        assertEquals(2, abbey.files)
        assertEquals(2, abbey.fields.getValue("Title").count)
        assertEquals(2, abbey.fields.getValue("Year").count) // TYER + TDRC both count
        assertEquals(1, abbey.fields.getValue("Genre").count)
        assertEquals(1, abbey.fields.getValue("Cover Art").count)
        assertEquals(50.0, abbey.fields.getValue("Genre").percent, 0.001)
        // Mean of 100,100,100,100,50,50,50 across the seven fields.
        assertEquals(550.0 / 7, abbey.percent, 0.001)

        val orphan = data.albums.single { it.album == NO_ALBUM }
        assertEquals(1, orphan.files)
        assertEquals(1, orphan.fields.getValue("Title").count)
        assertEquals(0, orphan.fields.getValue("Album").count)

        assertEquals(3, data.summaryFields.getValue("Title").count)
        assertEquals(1, data.summaryFields.getValue("Cover Art").count)
    }

    @Test
    fun albumCompletenessHandlesEmptyLibrary() {
        val data = albumCompleteness(emptyList())
        assertEquals(0, data.summaryFiles)
        assertEquals(0, data.summaryAlbums)
        assertTrue(data.albums.isEmpty())
        assertEquals(0.0, data.summaryPercent, 0.001)
    }

    @Test
    fun completenessTextRendersAlbumsAndSummary() {
        val text = renderCompletenessText(albumCompleteness(abbeyRoad()))
        assertTrue(text.contains("Abbey Road by The Beatles (2 file(s), 78.6% complete)"))
        assertTrue(text.contains("  Cover Art: 1/2 (50.0%)"))
        assertTrue(text.contains("(no album) (1 file(s), 14.3% complete)"))
        assertTrue(text.contains("All albums (2 album(s)) (3 file(s),"))
    }

    @Test
    fun duplicateGroupsUseNormalisedTitleAndArtist() {
        val files = listOf(
            item("d1", "TIT2" to "Come Together", "TPE1" to "The Beatles"),
            item("d2", "TIT2" to "come together!", "TPE1" to "THE BEATLES"),
            item("d3", "TIT2" to "Come Together", "TPE1" to "A Cover Band"),
            item("d4", "TPE1" to "The Beatles"), // no title: not enough evidence
        )
        val groups = duplicateGroups(files)
        assertEquals(1, groups.size)
        assertEquals("Come Together", groups[0].title)
        assertEquals("The Beatles", groups[0].artist)
        assertEquals(listOf("d1", "d2"), groups[0].itemIds)
    }

    @Test
    fun variantGroupsFindSpellingsOfOneValue() {
        val files = listOf(
            item("v1", "TPE1" to "The Beatles"),
            item("v2", "TPE1" to "the beatles"),
            item("v3", "TPE1" to "Beatles"), // different normalised value
            item("v4", "TPE1" to "Queen"), // one spelling only
            item("v5", "TPE1" to ""),
        )
        val groups = variantGroups(files, "Lead Performer")
        assertEquals(1, groups.size)
        assertEquals("the beatles", groups[0].normalized)
        assertEquals(setOf("The Beatles", "the beatles"), groups[0].spellings.keys)
        assertEquals(listOf("v1"), groups[0].spellings.getValue("The Beatles"))
        assertEquals(listOf("v2"), groups[0].spellings.getValue("the beatles"))
    }

    // ------------------------------------------------------------------
    // Jobs
    // ------------------------------------------------------------------

    @Test
    fun jobJsonRoundTrip() {
        val job = Job(
            name = "Fix the Beatles",
            treeUri = "content://com.android.externalstorage.documents/tree/primary%3AMusic",
            layers = listOf(
                JobCsvLayer(
                    csvUri = "content://docs/fixes.csv",
                    included = true,
                    roles = mapOf("Title" to Role.Match, "Genre" to Role.Write, "Comment" to Role.Skip),
                ),
                JobCsvLayer(csvUri = "content://docs/off.csv", included = false),
                JobPatternLayer("{Artist}/{Album}/{Track} - {Title}", included = true),
            ),
            alternativeNames = mapOf("TIT2" to "Title", "TPE1" to "Lead Performer"),
        )
        val restored = Job.fromJsonString(job.toJsonString())
        assertEquals(job, restored)
        // The JSON shape mirrors the app's own saved-state layer format,
        // so the UI can rebuild layers from a job the way it restores
        // its own state.
        val layersJson = JSONObject(job.toJsonString()).getJSONArray("layers")
        assertEquals("csv", layersJson.getJSONObject(0).getString("type"))
        assertEquals(2, layersJson.getJSONObject(0).getJSONObject("roles").getInt("Genre"))
        assertEquals("pattern", layersJson.getJSONObject(2).getString("type"))
    }

    @Test
    fun jobJsonDefaultsAndUnknownLayers() {
        // A minimal job: everything but the name falls back.
        val minimal = Job.fromJsonString("""{"name":"Bare"}""")
        assertEquals("Bare", minimal.name)
        assertEquals("", minimal.treeUri)
        assertTrue(minimal.layers.isEmpty())
        assertEquals(TagNames.defaultAlternativeNames, minimal.alternativeNames)

        // Unknown layer kinds are skipped, known ones survive; a role
        // integer outside the shared values degrades to Skip.
        val mixed = Job.fromJsonString(
            """{"name":"Mixed","layers":[
                {"type":"future-kind","included":true},
                {"type":"csv","id":"content://x.csv","roles":{"Title":99}}
            ]}"""
        )
        assertEquals(1, mixed.layers.size)
        val csv = mixed.layers.single() as JobCsvLayer
        assertEquals("content://x.csv", csv.csvUri)
        assertTrue(csv.included) // missing "included" means included
        assertEquals(Role.Skip, csv.roles.getValue("Title"))
    }
}
