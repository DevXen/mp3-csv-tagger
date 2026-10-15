package com.devxen.mp3csvtagger.tagio

import com.devxen.mp3csvtagger.engine.TagNames
import org.jaudiotagger.audio.AudioFileIO
import org.jaudiotagger.tag.TagField
import org.jaudiotagger.tag.id3.AbstractID3v2Frame
import org.jaudiotagger.tag.id3.AbstractID3v2Tag
import org.jaudiotagger.tag.id3.framebody.AbstractFrameBodyTextInfo
import org.jaudiotagger.tag.id3.framebody.FrameBodyCOMM
import org.jaudiotagger.tag.id3.framebody.FrameBodyTXXX
import org.jaudiotagger.tag.id3.framebody.FrameBodyUSLT
import java.io.File

/** One tag write: set [tagName] (frame [frame], or a TXXX described by tagName) to [value]. */
data class TagChange(val frame: String, val tagName: String, val value: String)

/**
 * Tag reading/writing through jaudiotagger, on real [File]s.
 *
 * Used for two things:
 * - the fallback reader for files the stream reader cannot parse (the
 *   caller copies such a file to a temp file first), and
 * - ALL writing: Apply copies a changed file to a temp file, lets
 *   jaudiotagger rewrite its tag there (preserving artwork and every
 *   frame we do not touch), then streams the result back to the document.
 *   One open, one commit per file.
 */
object JauTagIO {

    /** Read a file's text tags (same key convention as [Id3Reader.readTags]). */
    fun readTags(file: File): Map<String, String> {
        val audioFile = AudioFileIO.read(file)
        val tag = audioFile.tag ?: return emptyMap()
        val result = LinkedHashMap<String, String>()
        val fields = tag.fields
        while (fields.hasNext()) {
            val field = fields.next()
            val frameId = field.id
            if (frameId in TagNames.ignoredFrames) continue
            val frame = field as? AbstractID3v2Frame ?: continue
            when (val body = frame.body) {
                is FrameBodyTXXX -> {
                    val desc = body.description ?: ""
                    if (desc.isNotEmpty()) result[desc] = clean(body.text)
                }
                is FrameBodyCOMM -> result[frameId] = clean(body.text)
                is FrameBodyUSLT -> result[frameId] = clean(body.lyric) // USLT calls its text "lyric"
                is AbstractFrameBodyTextInfo -> result[frameId] = clean(body.textWithoutTrailingNulls)
                else -> Unit // non-text frame: nothing readable to expose
            }
        }
        return result
    }

    /** Apply [changes] to [file]'s tag and commit, in a single save. */
    fun writeTags(file: File, changes: List<TagChange>) {
        val audioFile = AudioFileIO.read(file)
        // getTagOrCreateAndSetDefault gives a file with no header a fresh
        // ID3v2 tag instead of failing — the "no header" case is normal.
        val tag = audioFile.getTagOrCreateAndSetDefault()
        val id3 = tag as? AbstractID3v2Tag
            ?: throw IllegalStateException("File does not carry an ID3v2 tag")

        for (change in changes) {
            if (change.frame == "TXXX") {
                writeCustomField(id3, change)
            } else {
                writeStandardFrame(id3, change)
            }
        }
        audioFile.commit()
    }

    /** Write a TXXX custom field, replacing only the entry with the same description. */
    private fun writeCustomField(id3: AbstractID3v2Tag, change: TagChange) {
        // Keep every other TXXX entry; drop only ours before re-adding, so
        // a file's unrelated custom fields survive the run.
        // getFrame() returns null (not an empty list) when no TXXX frame
        // exists yet — a Java platform type, so guard the call explicitly.
        val existing: List<TagField> = try {
            id3.getFrame("TXXX") ?: emptyList()
        } catch (e: NullPointerException) {
            emptyList()
        }
        val others: List<TagField> = existing.filter { field ->
            val body = (field as? AbstractID3v2Frame)?.body as? FrameBodyTXXX
            body?.description != change.tagName
        }
        val frame = id3.createFrame("TXXX")
        val body = frame.body as FrameBodyTXXX
        body.description = change.tagName
        body.text = change.value
        // Replace the whole TXXX set in one call: other descriptions kept,
        // ours updated. (Setting frames one at a time would risk jaudiotagger
        // treating each set as "replace all frames with this id".)
        id3.removeFrame("TXXX")
        id3.setFrame("TXXX", others + frame)
    }

    /** Write a standard text frame, replacing its previous value. */
    private fun writeStandardFrame(id3: AbstractID3v2Tag, change: TagChange) {
        val frame = id3.createFrame(change.frame)
        when (val body = frame.body) {
            is FrameBodyCOMM -> body.text = change.value
            is FrameBodyUSLT -> body.lyric = change.value
            is AbstractFrameBodyTextInfo -> body.text = change.value
            else -> throw IllegalStateException("Frame ${change.frame} does not hold text")
        }
        id3.removeFrame(change.frame)
        id3.setFrame(frame)
    }

    /** Multi-value text arrives NUL-separated; the shared convention joins values directly. */
    private fun clean(text: String?): String = (text ?: "").replace("\u0000", "")
}
