package com.devxen.mp3csvtagger.engine

/**
 * Tags-vs-path consistency: do the tags agree with the file layout?
 *
 * Many libraries encode the same facts twice — once in folder and file
 * names (`Artist/Album/01 - Title.mp3`) and once in the tags inside the
 * files. When the two disagree, one of them is wrong, and a tagging run
 * built on the wrong one makes the mess permanent. This file compares
 * the two, read-only:
 *
 * [checkConsistency] captures values from each file's path with a
 * filename pattern (the same [matchFilenamePattern] the preview's
 * pattern layers use) and compares each captured value against the
 * value actually stored in the file's tags, using the same loose
 * comparison as matching ([Matching.normalize] — case and punctuation
 * do not count as disagreements).
 *
 * Read-only is structural here, not just a promise: this file imports
 * nothing from the tagio package and nothing that can build a preview
 * or a write — it only reads [Mp3Item]s the UI already scanned. A
 * consistency report can therefore never change a file; it can only
 * point at the disagreements and let the user decide which side is
 * right. (The desktop consistency module makes the same guarantee by
 * restricting its own imports; a test pins the equivalent rule here by
 * scanning this file's source for forbidden imports.)
 */

/**
 * One tag whose path-captured value disagrees with its stored value.
 *
 * [pathValue] is the value the file's path/name claims the tag holds;
 * [tagValue] is the value actually stored in the file (which may be
 * empty — an empty tag under a path that names a value is a
 * disagreement, not a pass).
 */
data class ConsistencyMismatch(
    val itemId: String,
    val tag: String,
    val pathValue: String,
    val tagValue: String,
)

/** The outcome of a consistency check over a set of files. */
data class ConsistencyResult(
    val mismatches: List<ConsistencyMismatch>,
    /** How many files' paths matched the pattern and were compared. */
    val checked: Int,
    /** Item ids whose path did NOT match the pattern (not compared). */
    val unmatched: List<String>,
    /** Total files examined ([checked] + [unmatched] size). */
    val filesChecked: Int,
)

/**
 * Compare each file's tags against the values its path captures.
 *
 * [pattern] is a filename pattern in the usual form
 * (`"{Artist}/{Album}/{Track} - {Title}"`); it is matched against each
 * file's relative path from [relativePaths] (falling back to the
 * display name, the same fallback [buildPreview] uses), so folder
 * names can be captured too.
 *
 * For every captured tag, the captured value and the stored value
 * (read via [Mp3Item.valueFor], honouring [alternativeNames]) are
 * compared after [Matching.normalize]. A tag is skipped only when
 * *both* sides normalise to empty; any other disagreement — including
 * a stored value that is empty while the path names one — is recorded
 * as a mismatch, in file order, then pattern order.
 *
 * Files whose path does not match the pattern are not compared at
 * all; their ids are listed in the result's `unmatched`.
 */
fun checkConsistency(
    files: List<Mp3Item>,
    relativePaths: Map<String, String> = emptyMap(),
    pattern: String,
    alternativeNames: Map<String, String> = TagNames.defaultAlternativeNames,
): ConsistencyResult {
    val mismatches = mutableListOf<ConsistencyMismatch>()
    val unmatched = mutableListOf<String>()
    var checked = 0
    for (item in files) {
        val relativePath = relativePaths[item.id] ?: item.displayName
        val captures = matchFilenamePattern(pattern, relativePath)
        if (captures == null) {
            unmatched += item.id
            continue
        }
        checked++
        for ((tagName, pathValue) in captures) {
            val frame = TagNames.frameForTagName(tagName, alternativeNames)
            val tagValue = item.valueFor(tagName, frame)
            // Both sides effectively empty: nothing to compare.
            if (Matching.normalize(pathValue).isEmpty() && Matching.normalize(tagValue).isEmpty()) continue
            if (Matching.normalize(pathValue) == Matching.normalize(tagValue)) continue
            mismatches += ConsistencyMismatch(item.id, tagName, pathValue, tagValue)
        }
    }
    return ConsistencyResult(mismatches, checked, unmatched, files.size)
}
