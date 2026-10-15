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
 * One embedded cover image, carried as raw bytes plus the APIC fields a
 * faithful copy needs. Used only by tag sync's cover path: the bytes are
 * read from a paired SOURCE file at apply time and written to its target
 * twin — they are never part of a scan or a preview (see engine Sync.kt).
 */
data class CoverArtwork(
    val bytes: ByteArray,
    val mimeType: String,
    val pictureType: Int,
    val description: String,
) {
    // ByteArray in a data class: identity equals/hashCode, which is fine —
    // artwork is read, written and discarded, never compared.
    override fun equals(other: Any?): Boolean = this === other
    override fun hashCode(): Int = bytes.size
}

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

    /** True when [file]'s tag carries at least one artwork image. */
    fun hasArtwork(file: File): Boolean {
        val tag = AudioFileIO.read(file).tag ?: return false
        return tag.artworkList.isNotEmpty()
    }

    /**
     * Read [file]'s first embedded cover image, or null when it has none.
     * This loads the image bytes — callers do it lazily, for one paired
     * file at a time, only while applying a sync cover change.
     */
    fun readArtwork(file: File): CoverArtwork? {
        val tag = AudioFileIO.read(file).tag ?: return null
        val artwork = tag.firstArtwork ?: return null
        val bytes = artwork.binaryData ?: return null
        return CoverArtwork(
            bytes = bytes,
            mimeType = artwork.mimeType ?: "image/jpeg",
            pictureType = artwork.pictureType,
            description = artwork.description ?: "",
        )
    }

    /**
     * Replace [file]'s cover art with [artwork] and commit, in a single
     * save. Any previous APIC frames are removed first, so the file ends
     * with exactly the source file's cover — the same "replace" rule the
     * text-frame writers follow. Every other frame is preserved.
     */
    fun writeArtwork(file: File, artwork: CoverArtwork) {
        val audioFile = AudioFileIO.read(file)
        val tag = audioFile.getTagOrCreateAndSetDefault()
        try {
            tag.deleteArtworkField()
        } catch (e: Exception) {
            // No artwork field to delete (or a tag type that cannot hold
            // one and will fail at setField below anyway): keep going.
            if (tag.artworkList.isNotEmpty()) throw e
        }
        val newArtwork = org.jaudiotagger.tag.images.ArtworkFactory.getNew()
        newArtwork.binaryData = artwork.bytes
        newArtwork.mimeType = artwork.mimeType
        newArtwork.pictureType = artwork.pictureType
        newArtwork.description = artwork.description
        tag.setField(newArtwork)
        audioFile.commit()
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
