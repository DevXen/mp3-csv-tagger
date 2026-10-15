package com.devxen.mp3csvtagger.tagio

import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.InputStream
import java.io.OutputStream

/**
 * Tag-snapshot undo.
 *
 * Apply never copies audio files for backup — copying a big library would
 * take forever and gigabytes, for the sake of a few kilobytes of tags.
 * Instead, before a run modifies a file, we snapshot ONLY its tag data:
 * the raw bytes of every ID3 frame except APIC (cover art) and PRIV,
 * which are small. One snapshot file per run sits in the run's
 * log/backup folder next to the change-log CSV.
 *
 * The single exception: if a run itself changes a file's cover art, that
 * file's old APIC frame is included in its snapshot (see
 * [Id3Reader.readRawBlock]'s includeArtwork flag) — only files whose art
 * changes ever pay the size cost. No current feature edits cover art, so
 * in practice snapshots stay tiny.
 *
 * Restoring writes the snapshot's tag block back and then streams the
 * file's CURRENT audio bytes after it (everything past the current tag
 * block). The audio is never stored in the snapshot and never modified —
 * it is only passed through, because writing a document through SAF means
 * streaming its content. Files whose size or modification time changed
 * since the run are skipped with a warning (their audio may have been
 * replaced by another app), unless the user forces the restore.
 *
 * A file that had NO ID3 header at snapshot time is recorded with a null
 * block: restoring removes the header the run created, returning the file
 * to its exact original bytes-after-the-audio-start state.
 */
data class SnapshotEntry(
    /** Item id (on Android: the SAF document URI string). */
    val itemId: String,
    val displayName: String,
    /** File length at snapshot time; -1 when the provider did not report one. */
    val fileSize: Long,
    /** File mtime (epoch millis) at snapshot time; -1 when unknown. */
    val fileMtime: Long,
    /** Rebuilt ID3 tag block (header + frames), or null = file had no header. */
    val tagBlock: ByteArray?,
) {
    // ByteArray in a data class: equals/hashCode are identity-based, which
    // is fine — entries are written and read, never compared for equality.
    override fun equals(other: Any?): Boolean = this === other
    override fun hashCode(): Int = itemId.hashCode()
}

/** Serialisation for one run's snapshot. Compact binary format ("MCTS1"). */
object TagSnapshot {

    private const val MAGIC = "MCTS1"

    fun write(entries: List<SnapshotEntry>, out: OutputStream) {
        DataOutputStream(out).use { data ->
            data.writeUTF(MAGIC)
            data.writeInt(entries.size)
            for (entry in entries) {
                data.writeUTF(entry.itemId)
                data.writeUTF(entry.displayName)
                data.writeLong(entry.fileSize)
                data.writeLong(entry.fileMtime)
                val block = entry.tagBlock
                data.writeInt(block?.size ?: -1)
                if (block != null) data.write(block)
            }
        }
    }

    fun read(stream: InputStream): List<SnapshotEntry> {
        DataInputStream(stream).use { data ->
            require(data.readUTF() == MAGIC) { "Not a tag-snapshot file" }
            val count = data.readInt()
            return List(count) {
                val itemId = data.readUTF()
                val displayName = data.readUTF()
                val size = data.readLong()
                val mtime = data.readLong()
                val blockSize = data.readInt()
                val block = if (blockSize >= 0) ByteArray(blockSize).also { data.readFully(it) } else null
                SnapshotEntry(itemId, displayName, size, mtime, block)
            }
        }
    }

    /**
     * Write [entry]'s restored content into [out]: the snapshot tag block
     * (nothing, if the file originally had no header), followed by the
     * audio portion of the file as it exists NOW.
     *
     * [openStream] must supply a FRESH stream over the file's current
     * content on each call: this function opens it twice — once to measure
     * the current tag block, once to copy the audio after it. The guard
     * check ([unchanged]) is the caller's job, before opening any output:
     * SAF outputs truncate, so a skipped file must never get this far.
     */
    fun restore(entry: SnapshotEntry, openStream: () -> InputStream, out: OutputStream) {
        val audioStart = openStream().use { Id3Reader.tagBlockSize(it) }
        if (entry.tagBlock != null) out.write(entry.tagBlock)
        openStream().use { stream ->
            var remaining = audioStart.toLong()
            while (remaining > 0) {
                val skipped = stream.skip(remaining)
                if (skipped <= 0) break
                remaining -= skipped
            }
            stream.copyTo(out)
        }
    }

    /** Guard: true when the file still looks like the one the run touched. */
    fun unchanged(entry: SnapshotEntry, currentSize: Long, currentMtime: Long): Boolean {
        if (entry.fileSize >= 0 && currentSize >= 0 && entry.fileSize != currentSize) return false
        if (entry.fileMtime >= 0 && currentMtime >= 0 && entry.fileMtime != currentMtime) return false
        return true
    }
}
