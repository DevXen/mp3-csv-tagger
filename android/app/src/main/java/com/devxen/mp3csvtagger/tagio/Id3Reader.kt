package com.devxen.mp3csvtagger.tagio

import com.devxen.mp3csvtagger.engine.TagNames
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.nio.charset.Charset

/**
 * Reading ID3v2 tags from a stream, and capturing a file's raw tag block.
 *
 * Why not read everything through jaudiotagger? On Android the files live
 * behind SAF document URIs — streams, not java.io.File — and jaudiotagger
 * needs a File. Copying every MP3 to a temp file just to *read* its tags
 * would copy gigabytes for a big library. The ID3v2 tag, though, sits at
 * the very start of the file, so this reader pulls only the tag block
 * (usually a few KB) from the stream and parses the text frames itself.
 *
 * Files this reader cannot handle (ID3v2.2, whole-tag unsynchronisation,
 * anything malformed) raise [FallbackNeeded]; the caller then falls back
 * to a jaudiotagger read of a temp copy for that one file. Writing always
 * goes through jaudiotagger ([JauTagIO]), which preserves every frame we
 * do not touch.
 *
 * The same frame walk powers the undo snapshot: the raw bytes of every
 * frame except APIC/PRIV are kept verbatim, so a snapshot is kilobytes
 * where a file copy would be megabytes. See [TagSnapshot].
 */
class FallbackNeeded(message: String) : Exception(message)

/** A parsed ID3v2 tag block: version plus the raw bytes of its frames. */
class RawTagBlock(
    val versionMajor: Int,
    /** Frame id -> raw frame bytes (header + body), in file order. */
    val frames: List<Pair<String, ByteArray>>,
    /** Bytes of the original block header (10) + frames + padding. */
    val totalBlockSize: Int,
)

object Id3Reader {

    // ------------------------------------------------------------------
    // Public API
    // ------------------------------------------------------------------

    /**
     * The result of scanning one file's tag block: its text tags plus
     * whether it carries embedded cover art.
     *
     * Cover presence is all the scan records — never the image bytes.
     * Artwork can be megabytes per file, and everything the app decides
     * from a scan (completeness, tag sync) only needs to know art is
     * there; the bytes are read lazily, per file, only when a sync run
     * is actually applying one (see MainActivity's cover apply path).
     */
    data class TagScan(
        val tags: Map<String, String>,
        /** True when the tag block contains an APIC (picture) frame. */
        val hasCover: Boolean,
    )

    /**
     * Read a file's text tags from [stream]. Returns an empty map when the
     * file has no ID3v2 header. Keys are frame ids ("TIT2") or, for TXXX
     * frames, the frame description ("Subgenre") — the shared tag-name
     * convention. PRIV and APIC frames are ignored.
     */
    fun readTags(stream: InputStream): Map<String, String> = readScan(stream).tags

    /**
     * Read a file's tags AND cover presence in one pass over the tag
     * block. Cover presence comes free here: the frame walk already
     * visits every frame header, so spotting an APIC frame costs
     * nothing and retains no bytes. Everything else behaves exactly
     * like [readTags], including the [FallbackNeeded] cases.
     */
    fun readScan(stream: InputStream): TagScan {
        val block = readBlock(stream, stopAfterTag = true) ?: return TagScan(emptyMap(), hasCover = false)
        val result = LinkedHashMap<String, String>()
        for ((frameId, rawFrame) in block.frames) {
            if (frameId in TagNames.ignoredFrames) continue
            val body = frameBody(block.versionMajor, rawFrame)
            val pair = decodeTextFrame(frameId, body) ?: continue
            val (name, value) = pair
            if (name.isNotEmpty()) result[name] = value
        }
        return TagScan(result, hasCover = block.frames.any { it.first == "APIC" })
    }

    /**
     * Read just the raw tag block (header + frames, no audio) from the
     * start of [stream] — the basis of an undo snapshot. Returns null when
     * the file has no ID3v2 header.
     *
     * APIC and PRIV frames are EXCLUDED from the returned block: artwork
     * can be megabytes and private frames are not ours to restore. The one
     * exception the format allows: pass [includeArtwork] when a run is
     * itself changing cover art for this file (no v1 feature does), so its
     * old artwork can be restored too.
     */
    fun readRawBlock(stream: InputStream, includeArtwork: Boolean = false): ByteArray? {
        val block = readBlock(stream, stopAfterTag = true) ?: return null
        val kept = block.frames.filter { (id, _) ->
            id != "PRIV" && (includeArtwork || id != "APIC")
        }
        return rebuildBlock(block.versionMajor, kept)
    }

    /**
     * The whole original tag block, byte for byte, with no frame filtering.
     *
     * Fallback for headers the frame parser refuses (ID3v2.2, whole-tag
     * unsynchronisation): an undo snapshot built from this restores the
     * file's tags exactly, at the price of including any APIC bytes in
     * those rare files. Correctness of the undo beats snapshot size for
     * files we cannot parse. Returns null when there is no ID3v2 header.
     */
    fun readRawBlockVerbatim(stream: InputStream): ByteArray? {
        val header = ByteArray(10)
        if (readFully(stream, header) < 10 || !isId3Header(header)) return null
        val size = synchsafe(header, 6)
        val rest = ByteArray(size)
        val got = readFully(stream, rest)
        return header + rest.copyOf(got)
    }

    /** Size in bytes of the ID3v2 block at the start of [stream] (0 if none). */
    fun tagBlockSize(stream: InputStream): Int {
        val header = ByteArray(10)
        val read = readFully(stream, header)
        if (read < 10 || !isId3Header(header)) return 0
        return 10 + synchsafe(header, 6)
    }

    // ------------------------------------------------------------------
    // Block reading
    // ------------------------------------------------------------------

    private fun isId3Header(bytes: ByteArray): Boolean =
        bytes.size >= 3 && bytes[0] == 'I'.code.toByte() &&
            bytes[1] == 'D'.code.toByte() && bytes[2] == '3'.code.toByte()

    private fun synchsafe(bytes: ByteArray, offset: Int): Int =
        ((bytes[offset].toInt() and 0x7F) shl 21) or
            ((bytes[offset + 1].toInt() and 0x7F) shl 14) or
            ((bytes[offset + 2].toInt() and 0x7F) shl 7) or
            (bytes[offset + 3].toInt() and 0x7F)

    private fun readFully(stream: InputStream, buffer: ByteArray): Int {
        var total = 0
        while (total < buffer.size) {
            val n = stream.read(buffer, total, buffer.size - total)
            if (n < 0) break
            total += n
        }
        return total
    }

    /**
     * Read the header and frame area. With [stopAfterTag] we read only the
     * tag's own bytes — never the audio that follows.
     */
    private fun readBlock(stream: InputStream, stopAfterTag: Boolean): RawTagBlock? {
        val header = ByteArray(10)
        if (readFully(stream, header) < 10 || !isId3Header(header)) return null
        val version = header[3].toInt()
        if (version != 3 && version != 4) {
            throw FallbackNeeded("ID3v2.$version is not handled by the stream reader")
        }
        val flags = header[5].toInt()
        if (flags and 0x80 != 0) throw FallbackNeeded("unsynchronised tag")
        val tagSize = synchsafe(header, 6)
        val area = ByteArray(tagSize)
        if (readFully(stream, area) < tagSize) throw FallbackNeeded("truncated tag")

        var pos = 0
        // Extended header: v2.3 stores a plain size that excludes its own
        // 4 bytes; v2.4 stores a synchsafe size that includes them.
        if (flags and 0x40 != 0) {
            if (version == 3) {
                val extSize = bigEndianInt(area, 0)
                pos = 4 + extSize
            } else {
                pos = synchsafe(area, 0)
            }
        }
        val frames = mutableListOf<Pair<String, ByteArray>>()
        while (pos + 10 <= tagSize) {
            val id = String(area, pos, 4, Charsets.ISO_8859_1)
            if (!id.all { it in 'A'..'Z' || it in '0'..'9' }) break // padding or junk
            val frameSize = if (version == 4) synchsafe(area, pos + 4) else bigEndianInt(area, pos + 4)
            if (frameSize < 0 || pos + 10 + frameSize > tagSize) break
            frames += id to area.copyOfRange(pos, pos + 10 + frameSize)
            pos += 10 + frameSize
        }
        return RawTagBlock(version, frames, 10 + tagSize)
    }

    private fun bigEndianInt(bytes: ByteArray, offset: Int): Int =
        ((bytes[offset].toInt() and 0xFF) shl 24) or
            ((bytes[offset + 1].toInt() and 0xFF) shl 16) or
            ((bytes[offset + 2].toInt() and 0xFF) shl 8) or
            (bytes[offset + 3].toInt() and 0xFF)

    private fun frameBody(version: Int, rawFrame: ByteArray): ByteArray {
        val size = if (version == 4) synchsafe(rawFrame, 4) else bigEndianInt(rawFrame, 4)
        return rawFrame.copyOfRange(10, 10 + size.coerceAtMost(rawFrame.size - 10))
    }

    /** Rebuild a complete ID3v2 block (header + given raw frames). */
    private fun rebuildBlock(version: Int, frames: List<Pair<String, ByteArray>>): ByteArray {
        val bodySize = frames.sumOf { it.second.size }
        val out = ByteArrayOutputStream(10 + bodySize)
        out.write(byteArrayOf('I'.code.toByte(), 'D'.code.toByte(), '3'.code.toByte()))
        out.write(version)
        out.write(0) // revision
        out.write(0) // flags: none — frame-level bytes carry what matters
        // Synchsafe size.
        out.write((bodySize shr 21) and 0x7F)
        out.write((bodySize shr 14) and 0x7F)
        out.write((bodySize shr 7) and 0x7F)
        out.write(bodySize and 0x7F)
        for ((_, raw) in frames) out.write(raw)
        return out.toByteArray()
    }

    // ------------------------------------------------------------------
    // Text frame decoding
    // ------------------------------------------------------------------

    private fun decodeTextFrame(frameId: String, body: ByteArray): Pair<String, String>? {
        if (body.isEmpty()) return null
        val encoding = body[0].toInt()
        val charset = charsetFor(encoding)
        fun terminatorLength() = if (encoding == 1 || encoding == 2) 2 else 1
        fun findTerminator(from: Int): Int {
            var i = from
            while (i < body.size) {
                if (encoding == 1 || encoding == 2) {
                    if (i + 1 < body.size && body[i].toInt() == 0 && body[i + 1].toInt() == 0) return i
                    i += 2
                } else {
                    if (body[i].toInt() == 0) return i
                    i++
                }
            }
            return body.size
        }
        fun decode(bytes: ByteArray): String =
            String(bytes, charset).replace("\u0000", "")

        return when {
            frameId == "TXXX" -> {
                val descEnd = findTerminator(1)
                val desc = decode(body.copyOfRange(1, descEnd))
                val valueStart = minOf(descEnd + terminatorLength(), body.size)
                desc to decode(body.copyOfRange(valueStart, body.size))
            }
            frameId == "COMM" || frameId == "USLT" -> {
                // encoding(1) + language(3) + description(terminated) + text
                if (body.size < 4) return null
                val descEnd = findTerminator(4)
                val valueStart = minOf(descEnd + terminatorLength(), body.size)
                frameId to decode(body.copyOfRange(valueStart, body.size))
            }
            frameId.startsWith("T") -> frameId to decode(body.copyOfRange(1, body.size))
            else -> null // non-text frame: not a tag we read or write
        }
    }

    private fun charsetFor(encoding: Int): Charset = when (encoding) {
        0 -> Charsets.ISO_8859_1
        1 -> Charsets.UTF_16 // BOM-aware
        2 -> Charsets.UTF_16BE
        else -> Charsets.UTF_8
    }
}
