package com.devxen.mp3csvtagger

import com.devxen.mp3csvtagger.tagio.Id3Reader
import com.devxen.mp3csvtagger.tagio.JauTagIO
import com.devxen.mp3csvtagger.tagio.SnapshotEntry
import com.devxen.mp3csvtagger.tagio.TagChange
import com.devxen.mp3csvtagger.tagio.TagSnapshot
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File

/**
 * Tag IO tests on real files: silent-MP3 bytes on disk, tags written with
 * jaudiotagger, read back two ways (jaudiotagger and the stream reader),
 * then a tag-snapshot capture/modify/restore cycle.
 */
class TagIoTest {

    /** One MPEG-1 Layer III frame of silence, repeated — an MP3-shaped file. */
    private fun silentMp3(): ByteArray {
        val frame = byteArrayOf(0xFF.toByte(), 0xFB.toByte(), 0x90.toByte(), 0x00) + ByteArray(413)
        val out = ByteArrayOutputStream()
        repeat(20) { out.write(frame) }
        return out.toByteArray()
    }

    private fun tempMp3(bytes: ByteArray = silentMp3()): File {
        val file = File.createTempFile("tagio", ".mp3")
        file.deleteOnExit()
        file.writeBytes(bytes)
        return file
    }

    @Test
    fun writeThenReadBackBothWays() {
        val file = tempMp3()
        // A file with no ID3 header must be writable, not an error.
        JauTagIO.writeTags(
            file,
            listOf(
                TagChange("TIT2", "Title", "Township Rebellion"),
                TagChange("TPE1", "Lead Performer", "Rage Against the Machine"),
                TagChange("TCON", "Genre", "Rock"),
                TagChange("TXXX", "Subgenre", "Political Rap Metal"),
            ),
        )
        val viaJau = JauTagIO.readTags(file)
        assertEquals("Township Rebellion", viaJau["TIT2"])
        assertEquals("Political Rap Metal", viaJau["Subgenre"])

        val viaStream = file.inputStream().use { Id3Reader.readTags(it) }
        assertEquals(viaJau, viaStream)
    }

    @Test
    fun customFieldUpdateKeepsOtherCustomFields() {
        val file = tempMp3()
        JauTagIO.writeTags(file, listOf(TagChange("TXXX", "Rating", "4"), TagChange("TXXX", "Mood", "Loud")))
        JauTagIO.writeTags(file, listOf(TagChange("TXXX", "Rating", "5")))
        val tags = JauTagIO.readTags(file)
        assertEquals("5", tags["Rating"])
        assertEquals("Loud", tags["Mood"])
    }

    @Test
    fun streamReaderParsesHandBuiltV23Tag() {
        // Build an ID3v2.3 block by hand (UTF-8 text, encoding byte 3) so the
        // stream reader is tested against bytes no library produced.
        fun frame(id: String, body: ByteArray): ByteArray {
            val out = ByteArrayOutputStream()
            out.write(id.toByteArray(Charsets.US_ASCII))
            out.write(byteArrayOf(0, 0, (body.size shr 8).toByte(), body.size.toByte()))
            out.write(byteArrayOf(0, 0))
            out.write(body)
            return out.toByteArray()
        }
        fun textFrame(id: String, value: String) = frame(id, byteArrayOf(3) + value.toByteArray(Charsets.UTF_8))
        val frames = ByteArrayOutputStream()
        frames.write(textFrame("TIT2", "Bombtrack"))
        frames.write(frame("TXXX", byteArrayOf(3) + "Rating".toByteArray() + byteArrayOf(0) + "5".toByteArray()))
        val frameBytes = frames.toByteArray()
        val header = ByteArrayOutputStream()
        header.write("ID3".toByteArray())
        header.write(byteArrayOf(3, 0, 0))
        header.write(
            byteArrayOf(
                ((frameBytes.size shr 21) and 0x7F).toByte(), ((frameBytes.size shr 14) and 0x7F).toByte(),
                ((frameBytes.size shr 7) and 0x7F).toByte(), (frameBytes.size and 0x7F).toByte(),
            )
        )
        val tags = Id3Reader.readTags(ByteArrayInputStream(header.toByteArray() + frameBytes + silentMp3()))
        assertEquals("Bombtrack", tags["TIT2"])
        assertEquals("5", tags["Rating"])
    }

    @Test
    fun noHeaderFileReadsEmpty() {
        val file = tempMp3()
        assertTrue(file.inputStream().use { Id3Reader.readTags(it) }.isEmpty())
        assertEquals(0, file.inputStream().use { Id3Reader.tagBlockSize(it) })
    }

    @Test
    fun snapshotRestoreBringsTagsBackWithoutTouchingAudio() {
        val file = tempMp3()
        JauTagIO.writeTags(file, listOf(TagChange("TCON", "Genre", "Rock")))
        val audioAfterFirstWrite = file.readBytes()

        // Capture the snapshot exactly as Apply does.
        val block = file.inputStream().use { Id3Reader.readRawBlock(it) }
        val entry = SnapshotEntry(
            itemId = file.absolutePath, displayName = file.name,
            fileSize = file.length(), fileMtime = file.lastModified(),
            tagBlock = block,
        )
        // Serialise + reload the snapshot, then change the tags.
        val snapshotBytes = ByteArrayOutputStream().also { TagSnapshot.write(listOf(entry), it) }.toByteArray()
        val loaded = TagSnapshot.read(ByteArrayInputStream(snapshotBytes)).single()
        JauTagIO.writeTags(file, listOf(TagChange("TCON", "Genre", "Rap Metal")))
        assertEquals("Rap Metal", JauTagIO.readTags(file)["TCON"])

        // Restore into a new file image: snapshot block + current audio.
        val restored = ByteArrayOutputStream()
        TagSnapshot.restore(loaded, { file.inputStream() }, restored)
        val restoredFile = tempMp3(restored.toByteArray())
        assertEquals("Rock", JauTagIO.readTags(restoredFile)["TCON"])
        // Audio bytes are byte-identical: the audio is exactly the silent
        // stream, sitting at the end of both the pre-change and restored
        // files (each file is tag block + that same audio).
        val audio = silentMp3()
        assertArrayEquals(audio, audioAfterFirstWrite.copyOfRange(audioAfterFirstWrite.size - audio.size, audioAfterFirstWrite.size))
        assertArrayEquals(audio, restored.toByteArray().copyOfRange(restored.size() - audio.size, restored.size()))

        // Guard: a size change since the snapshot blocks a normal restore.
        val changed = loaded.copy(fileSize = loaded.fileSize + 1)
        assertFalse(TagSnapshot.unchanged(changed, file.length(), file.lastModified()))
        assertTrue(TagSnapshot.unchanged(loaded, file.length(), loaded.fileMtime))
    }
}
