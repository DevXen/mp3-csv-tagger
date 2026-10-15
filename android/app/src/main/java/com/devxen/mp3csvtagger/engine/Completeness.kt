package com.devxen.mp3csvtagger.engine

import java.util.Locale

/**
 * Read-only analysis of a scanned library: album completeness,
 * duplicates and spelling variants.
 *
 * Tagging a library is much easier once its existing problems are
 * visible. This file answers three questions about a list of scanned
 * [Mp3Item]s — without changing anything:
 *
 * * [albumCompleteness] — per album, which of the fields a finished
 *   album should have (title, artist, year, cover art, …) are actually
 *   filled in, and for what share of the album's files?
 * * [duplicateGroups] — which files appear to be the *same track*
 *   (same title and same lead performer, compared after
 *   [Matching.normalize], so case and punctuation differences do not
 *   hide a duplicate)?
 * * [variantGroups] — for one tag, which *values* are really the same
 *   value spelled more than one way ("Beatles" / "beatles" /
 *   "BEATLES!")? Those are the values a cleanup pass would want to
 *   unify — this file only reports them; renaming values is a
 *   decision for the user, never something a report does on its own.
 *
 * All three mirror the desktop program's library report, field for
 * field, so the two apps describe the same library the same way.
 * Like [checkConsistency], everything here is read-only by
 * construction: the file works on scanned items in memory and imports
 * nothing that can write a tag.
 */

/**
 * The fields a complete album is expected to carry, as
 * (display name, frame) pairs. The frame is null for Cover Art, which
 * is not a text frame at all: presence is judged with
 * [Mp3Item.hasCover] instead of a tag value. "Year" is special-cased
 * in [fieldPresent]: either TYER or TDRC counts, because libraries in
 * the wild use both for the release year.
 */
val COMPLETENESS_FIELDS: List<Pair<String, String?>> = listOf(
    "Title" to "TIT2",
    "Lead Performer" to "TPE1",
    "Album" to "TALB",
    "Year" to "TYER",
    "Genre" to "TCON",
    "Track Number" to "TRCK",
    "Cover Art" to null,
)

/**
 * Display name for the group of files that carry no album tag at all.
 * They still get a completeness row — an album-less file is exactly
 * the kind of finding this report exists to surface.
 */
const val NO_ALBUM = "(no album)"

/** How many of a group's files carry one field, and that as a percent. */
data class FieldStat(val count: Int, val percent: Double)

/** Completeness figures for one album group. */
data class AlbumCompleteness(
    /** Album name as stored on the group's first file, or [NO_ALBUM]. */
    val album: String,
    /** Lead performer as stored on the group's first file. */
    val artist: String,
    val files: Int,
    /** Field name -> stats, in [COMPLETENESS_FIELDS] order. */
    val fields: Map<String, FieldStat>,
    /** Mean of the field percents. */
    val percent: Double,
)

/** Completeness figures for a whole library. */
data class CompletenessData(
    val albums: List<AlbumCompleteness>,
    /** File count, album count and field stats over every file. */
    val summaryFiles: Int,
    val summaryAlbums: Int,
    val summaryFields: Map<String, FieldStat>,
    val summaryPercent: Double,
)

/** True when [item] carries a non-empty value for one completeness field. */
private fun fieldPresent(item: Mp3Item, name: String, frame: String?): Boolean {
    if (frame == null) return item.hasCover // Cover Art: presence, not a text value
    if (name == "Year") {
        // TYER and TDRC are both in use as the year; either one counts.
        return item.valueFor(name, frame).isNotBlank() ||
            item.valueFor("Recording Date", "TDRC").isNotBlank() ||
            (item.tags["TDRC"] ?: "").isNotBlank()
    }
    return item.valueFor(name, frame).isNotBlank()
}

/** Per-field counts/percents for [members], plus their mean percent. */
private fun fieldStats(members: List<Mp3Item>): Pair<Map<String, FieldStat>, Double> {
    val fields = LinkedHashMap<String, FieldStat>()
    for ((name, frame) in COMPLETENESS_FIELDS) {
        val count = members.count { fieldPresent(it, name, frame) }
        val percent = if (members.isEmpty()) 0.0 else 100.0 * count / members.size
        fields[name] = FieldStat(count, percent)
    }
    val percent = if (fields.isEmpty()) 0.0 else fields.values.sumOf { it.percent } / fields.size
    return fields to percent
}

/**
 * Measure how completely each album in [files] is tagged.
 *
 * Files are grouped by album, where the group key is
 * (normalised artist, normalised album) — so spelling variants of the
 * same artist/album land in one group — and a file with no album value
 * groups under [NO_ALBUM]. Each album entry's album/artist are the
 * as-stored spellings from the group's first file, its `fields` map
 * each completeness field name to the count and percent of the album's
 * files carrying a non-empty value, and its `percent` is the mean of
 * the field percents. The summary carries the same field stats
 * computed over every file, plus the total file and album counts.
 * Albums are sorted by (normalised) artist, then album.
 */
fun albumCompleteness(files: List<Mp3Item>): CompletenessData {
    val groups = LinkedHashMap<Pair<String, String>, MutableList<Mp3Item>>()
    for (item in files) {
        val artist = item.valueFor("Lead Performer", "TPE1")
        val album = item.valueFor("Album", "TALB")
        val key = Matching.normalize(artist) to Matching.normalize(album)
        groups.getOrPut(key) { mutableListOf() } += item
    }

    val albums = groups.entries.sortedWith(compareBy({ it.key.first }, { it.key.second })).map { (_, members) ->
        val first = members.first()
        val (fields, percent) = fieldStats(members)
        AlbumCompleteness(
            album = first.valueFor("Album", "TALB").ifEmpty { NO_ALBUM },
            artist = first.valueFor("Lead Performer", "TPE1"),
            files = members.size,
            fields = fields,
            percent = percent,
        )
    }

    val (summaryFields, summaryPercent) = fieldStats(files)
    return CompletenessData(
        albums = albums,
        summaryFiles = files.size,
        summaryAlbums = albums.size,
        summaryFields = summaryFields,
        summaryPercent = summaryPercent,
    )
}

/**
 * Render [albumCompleteness] output as a plain-text report: one block
 * per album — its overall percent, then each field's count and
 * percent — followed by the same figures for the whole library, so
 * both "which album needs work" and "how tagged is this library" can
 * be read off one report. (Same layout as the desktop renderer.)
 */
fun renderCompletenessText(data: CompletenessData): String {
    val lines = mutableListOf("Album completeness", "==================", "")

    // Locale.ROOT so the decimal point is always "." — the desktop
    // renderer is locale-independent too, and a report shared from the
    // phone should read the same whatever the phone's locale is.
    fun percentText(value: Double): String = "%.1f".format(Locale.ROOT, value)

    fun renderBlock(heading: String, filesCount: Int, fields: Map<String, FieldStat>, percent: Double) {
        lines += "$heading ($filesCount file(s), ${percentText(percent)}% complete)"
        for ((name, _) in COMPLETENESS_FIELDS) {
            val field = fields.getValue(name)
            lines += "  $name: ${field.count}/$filesCount (${percentText(field.percent)}%)"
        }
        lines += ""
    }

    for (album in data.albums) {
        val heading = if (album.artist.isNotEmpty()) "${album.album} by ${album.artist}" else album.album
        renderBlock(heading, album.files, album.fields, album.percent)
    }
    renderBlock(
        "All albums (${data.summaryAlbums} album(s))",
        data.summaryFiles, data.summaryFields, data.summaryPercent,
    )
    return lines.joinToString("\n").trimEnd('\n') + "\n"
}

/** Files that look like duplicate copies of the same track. */
data class DuplicateGroup(
    /** Title as stored on the group's first file. */
    val title: String,
    /** Lead performer as stored on the group's first file. */
    val artist: String,
    /** Item ids in scan order. */
    val itemIds: List<String>,
)

/**
 * Group files that look like duplicate copies of the same track.
 *
 * Two files are duplicates when their Title (TIT2) and Lead Performer
 * (TPE1) values are equal after [Matching.normalize] — values are
 * looked up via [Mp3Item.valueFor], so tags stored under either the
 * friendly name or the frame id are found. Files missing either value
 * are skipped: with no title or no artist there is not enough evidence
 * to call anything a duplicate.
 *
 * Only groups of more than one file are returned, sorted by
 * (normalised) artist, then title.
 */
fun duplicateGroups(files: List<Mp3Item>): List<DuplicateGroup> {
    val groups = LinkedHashMap<Pair<String, String>, MutableList<Mp3Item>>()
    for (item in files) {
        val title = item.valueFor("Title", "TIT2")
        val artist = item.valueFor("Lead Performer", "TPE1")
        val key = Matching.normalize(title) to Matching.normalize(artist)
        if (key.first.isEmpty() || key.second.isEmpty()) continue
        groups.getOrPut(key) { mutableListOf() } += item
    }
    return groups.values
        .filter { it.size > 1 }
        .map { members ->
            DuplicateGroup(
                title = members.first().valueFor("Title", "TIT2"),
                artist = members.first().valueFor("Lead Performer", "TPE1"),
                itemIds = members.map { it.id },
            )
        }
        .sortedWith(compareBy({ Matching.normalize(it.artist) }, { Matching.normalize(it.title) }))
}

/** One normalised value of a tag, spelled more than one way. */
data class VariantGroup(
    val tag: String,
    /** The shared normalised form the spellings collapse to. */
    val normalized: String,
    /** Spelling as stored -> item ids carrying it, in scan order. */
    val spellings: Map<String, List<String>>,
)

/**
 * Find values of [tagName] that are spelled more than one way.
 *
 * Files are grouped by the normalised form of their value for
 * [tagName] (resolved to a frame with [TagNames.frameForTagName],
 * honouring [alternativeNames] when given, and read via
 * [Mp3Item.valueFor]). A group is reported only when that one
 * normalised value occurs with more than one distinct actual spelling
 * — e.g. "Beatles", "beatles" and "BEATLES!" all normalise to
 * "beatles" but are three spellings. Empty values are skipped. Note
 * that normalisation only folds case and punctuation (see [Matching]):
 * "The Beatles" normalises to "the beatles", a *different* value from
 * "beatles".
 *
 * Groups are sorted by the normalised value; spellings are the values
 * as stored (stripped of surrounding whitespace).
 */
fun variantGroups(
    files: List<Mp3Item>,
    tagName: String,
    alternativeNames: Map<String, String> = TagNames.defaultAlternativeNames,
): List<VariantGroup> {
    val frame = TagNames.frameForTagName(tagName, alternativeNames)
    val byNormalized = LinkedHashMap<String, LinkedHashMap<String, MutableList<String>>>()
    for (item in files) {
        val value = item.valueFor(tagName, frame).trim()
        if (value.isEmpty()) continue
        val normalized = Matching.normalize(value)
        if (normalized.isEmpty()) continue
        byNormalized.getOrPut(normalized) { LinkedHashMap() }
            .getOrPut(value) { mutableListOf() } += item.id
    }
    return byNormalized.entries
        .filter { it.value.size > 1 }
        .sortedBy { it.key }
        .map { (normalized, spellings) -> VariantGroup(tagName, normalized, spellings) }
}
