package com.devxen.mp3csvtagger.engine

/**
 * Two-library tag sync: copy tags from one library onto its twin.
 *
 * The situation this is built for: the same library exists in two places
 * (a main copy and a backup / second-device / re-rip copy) and the *tags*
 * of one copy have been fixed up while the other copy's have not. Sync
 * pairs the two copies up file by file and works out the source copy's
 * tag values for the target copy — as a plain values map the UI feeds
 * into an ordinary preview over the target scan as a [ValuesSource]
 * named "tag sync", so the user sees every proposed change, can pick
 * candidates and override them with manual edits, and gets the usual
 * change log and snapshot undo when they apply it.
 *
 * Pairing is by *relative path*: `Music/Artist/Album/01 Song.mp3` in the
 * source library pairs with the same relative path in the target library,
 * compared case-insensitively with "/" separators, so a library moved
 * between a case-sensitive and a case-insensitive filesystem still pairs
 * up. Files that do not pair are reported as unpaired and are **never**
 * touched by a sync: unpaired ids appear in no values map. (The desktop
 * program additionally pairs leftovers by audio fingerprint; Android has
 * no fingerprint feature — see the project roadmap — so path pairing is
 * the whole story here.)
 *
 * Nothing in this file writes to any MP3, or even reads one: it works
 * purely on the scanned [Mp3Item]s the UI hands it, exactly like the
 * rest of the engine.
 */

/**
 * Source name recorded on every candidate a sync preview produces, so
 * the preview, the change log and the undo flow can all tell these
 * values apart from CSV values.
 */
const val SYNC_SOURCE_NAME = "tag sync"

/** Tag name used for cover art in sync differences and values. */
const val COVER_TAG_NAME = "Cover Art"

/**
 * Prefix of the opaque token a sync values map carries for cover art.
 *
 * Cover art is not text, so it cannot travel through a preview as a
 * literal value the way a title can. Instead the "Cover Art" entry's
 * value is this prefix followed by the *source item's id*: the apply
 * side (UI) resolves that id against the source scan it still holds,
 * reads that file's artwork bytes lazily (only for files actually being
 * written), and embeds them in the target file. The engine itself never
 * sees image bytes — a scan records only presence ([Mp3Item.hasCover])
 * and an equality token ([Mp3Item.coverKey]) — which is what keeps the
 * engine pure and the preview cheap.
 */
const val COVER_TOKEN_PREFIX = "cover:"

/** The sync-values token proposing [source]'s cover art for its twin. */
fun coverToken(source: Mp3Item): String = COVER_TOKEN_PREFIX + source.id

/** The source item id carried by a cover [token], or null if it is not one. */
fun coverTokenSourceId(token: String): String? =
    if (token.startsWith(COVER_TOKEN_PREFIX)) token.removePrefix(COVER_TOKEN_PREFIX) else null

/** One source file and the target file it is the twin of. */
data class SyncPair(
    /** The pairing key: the files' shared relative path (see [relativeKey]). */
    val relKey: String,
    val sourceId: String,
    val targetId: String,
)

/** How two libraries pair up: the pairs plus both leftover lists. */
data class SyncPlan(
    val pairs: List<SyncPair>,
    /** Source item ids with no target partner. Never touched by a sync. */
    val unpairedSource: List<String>,
    /** Target item ids with no source partner. Never touched by a sync. */
    val unpairedTarget: List<String>,
)

/**
 * The pairing key for a relative path: "/" separators, case-folded, so
 * `Artist/Album/Song.mp3` and `artist/album/song.mp3` — the same file on
 * filesystems that differ only in case handling — produce the same key.
 */
fun relativeKey(relativePath: String): String =
    relativePath.replace('\\', '/').lowercase()

/**
 * A file's relative path for pairing: the scanner-supplied path from
 * [relativePaths], falling back to the display name (a file at the
 * library root *is* its name, and a bare engine test knows nothing
 * else) — the same fallback [buildPreview] uses for filename patterns.
 */
private fun pathOf(item: Mp3Item, relativePaths: Map<String, String>): String =
    relativePaths[item.id] ?: item.displayName

/**
 * Pair two scanned libraries by relative path and return the plan.
 *
 * [sourceRelativePaths] / [targetRelativePaths] map item ids to paths
 * relative to their library's root (the scanner supplies them; paths
 * are a storage concern, so they travel beside [Mp3Item], not inside
 * it — same convention as [buildPreview]). Pairs follow the source
 * files' order; each target file pairs at most once, and on a key
 * collision (two target files whose relative paths differ only in
 * case) the first target wins, because the other cannot also be the
 * twin.
 */
fun pairLibraries(
    sourceFiles: List<Mp3Item>,
    targetFiles: List<Mp3Item>,
    sourceRelativePaths: Map<String, String> = emptyMap(),
    targetRelativePaths: Map<String, String> = emptyMap(),
): SyncPlan {
    val targetsByKey = LinkedHashMap<String, Mp3Item>()
    for (target in targetFiles) {
        targetsByKey.putIfAbsent(relativeKey(pathOf(target, targetRelativePaths)), target)
    }

    val pairs = mutableListOf<SyncPair>()
    val unpairedSource = mutableListOf<String>()
    val pairedTargetIds = mutableSetOf<String>()
    for (source in sourceFiles) {
        val key = relativeKey(pathOf(source, sourceRelativePaths))
        val target = targetsByKey[key]
        if (target == null || target.id in pairedTargetIds) {
            unpairedSource += source.id
            continue
        }
        pairedTargetIds += target.id
        pairs += SyncPair(relKey = key, sourceId = source.id, targetId = target.id)
    }
    val unpairedTarget = targetFiles.filter { it.id !in pairedTargetIds }.map { it.id }
    return SyncPlan(pairs, unpairedSource, unpairedTarget)
}

/**
 * The default tag set for a sync: every text tag found on paired source
 * files, in first-seen order. Callers render these as checkboxes and
 * pass the checked subset to [tagDifferences] / [buildSyncValues].
 * Cover art is not a text tag and is handled by the separate
 * includeCover flag, so it never appears here.
 */
fun defaultSyncTags(plan: SyncPlan, sourceFiles: List<Mp3Item>): List<String> {
    val byId = sourceFiles.associateBy { it.id }
    val tags = mutableListOf<String>()
    for (pair in plan.pairs) {
        val source = byId[pair.sourceId] ?: continue
        for (tagName in source.tags.keys) {
            if (tagName.isNotEmpty() && tagName !in tags) tags += tagName
        }
    }
    return tags
}

/**
 * Whether a pair's covers provably differ, from scan data alone.
 *
 * A difference is only claimed when it is *known*: the source has a
 * cover and the target either has none, or both sides supplied cover
 * keys ([Mp3Item.coverKey]) and they differ. When both files have a
 * cover but either key is missing, the covers might be identical —
 * the engine cannot hash bytes it deliberately never loads, and sync
 * must not propose a replacement it cannot justify, so the pair is
 * left alone.
 */
private fun coverDiffers(source: Mp3Item, target: Mp3Item): Boolean {
    if (!source.hasCover) return false
    if (!target.hasCover) return true
    val sourceKey = source.coverKey ?: return false
    val targetKey = target.coverKey ?: return false
    return sourceKey != targetKey
}

/** One (pair, tag) whose source value would be copied by a sync. */
data class TagDifference(
    val targetId: String,
    val sourceId: String,
    val tag: String,
    val sourceValue: String,
    val targetValue: String,
)

/**
 * List where paired files' tags differ (for display / dry runs).
 *
 * One [TagDifference] per (pair, tag) whose source value is non-empty
 * and differs from the target's — exactly the values [buildSyncValues]
 * would copy. With [includeCover], a pair whose covers provably differ
 * (see [coverDiffers]) also produces a row with tag "Cover Art"; its
 * values are display strings — the [COVER_PRESENT] marker for a side
 * that has a cover, "" for a side that has none — never image data.
 * Unpaired files never appear.
 */
fun tagDifferences(
    plan: SyncPlan,
    sourceFiles: List<Mp3Item>,
    targetFiles: List<Mp3Item>,
    tags: Collection<String>,
    includeCover: Boolean,
    alternativeNames: Map<String, String> = TagNames.defaultAlternativeNames,
): List<TagDifference> {
    val sources = sourceFiles.associateBy { it.id }
    val targets = targetFiles.associateBy { it.id }
    val differences = mutableListOf<TagDifference>()
    for (pair in plan.pairs) {
        val source = sources[pair.sourceId] ?: continue
        val target = targets[pair.targetId] ?: continue
        for (tagName in tags) {
            val frame = TagNames.frameForTagName(tagName, alternativeNames)
            val sourceValue = source.valueFor(tagName, frame)
            val targetValue = target.valueFor(tagName, frame)
            if (sourceValue.isNotEmpty() && sourceValue != targetValue) {
                differences += TagDifference(pair.targetId, pair.sourceId, tagName, sourceValue, targetValue)
            }
        }
        if (includeCover && coverDiffers(source, target)) {
            differences += TagDifference(
                targetId = pair.targetId,
                sourceId = pair.sourceId,
                tag = COVER_TAG_NAME,
                sourceValue = COVER_PRESENT,
                targetValue = if (target.hasCover) COVER_PRESENT else "",
            )
        }
    }
    return differences
}

/**
 * Build the sync values for a target preview:
 * `targetItemId -> (tag name -> value)`.
 *
 * The UI wraps the result in a [ValuesSource] named [SYNC_SOURCE_NAME]
 * and builds an ordinary preview over the *target* scan with it. A tag
 * is copied only when the source value is non-empty and differs from
 * the target value — copying an identical or empty value would either
 * be noise or would *erase* a target value the source never had, and
 * sync must never do either.
 *
 * Cover art: with [includeCover], when a pair's covers provably differ
 * and the source has one, the map's "Cover Art" entry for the target is
 * the opaque token from [coverToken] — the apply side resolves it to
 * the source file's artwork bytes (see [COVER_TOKEN_PREFIX]). When the
 * covers cannot be proven different, no entry is produced: sync does
 * not fake cover support it cannot verify from scan data.
 *
 * Unpaired files never appear in the map.
 */
fun buildSyncValues(
    plan: SyncPlan,
    sourceFiles: List<Mp3Item>,
    targetFiles: List<Mp3Item>,
    tags: Collection<String>,
    includeCover: Boolean,
    alternativeNames: Map<String, String> = TagNames.defaultAlternativeNames,
): Map<String, Map<String, String>> {
    val sources = sourceFiles.associateBy { it.id }
    val targets = targetFiles.associateBy { it.id }
    val valuesByTarget = LinkedHashMap<String, Map<String, String>>()
    for (pair in plan.pairs) {
        val source = sources[pair.sourceId] ?: continue
        val target = targets[pair.targetId] ?: continue
        val values = LinkedHashMap<String, String>()
        for (tagName in tags) {
            val frame = TagNames.frameForTagName(tagName, alternativeNames)
            val sourceValue = source.valueFor(tagName, frame)
            val targetValue = target.valueFor(tagName, frame)
            if (sourceValue.isNotEmpty() && sourceValue != targetValue) {
                values[tagName] = sourceValue
            }
        }
        if (includeCover && coverDiffers(source, target)) {
            values[COVER_TAG_NAME] = coverToken(source)
        }
        if (values.isNotEmpty()) valuesByTarget[pair.targetId] = values
    }
    return valuesByTarget
}
