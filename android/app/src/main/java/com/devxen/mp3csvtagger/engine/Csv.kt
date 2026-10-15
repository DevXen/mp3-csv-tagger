package com.devxen.mp3csvtagger.engine

import java.io.InputStream
import java.io.Reader

/**
 * CSV reading and writing, matching the desktop program's format:
 *
 * - UTF-8 (a UTF-8 BOM, as Excel writes, is tolerated),
 * - comma-separated with `"` quoting (quotes can contain commas, quotes
 *   doubled as `""`, and line breaks),
 * - first row is the header (column tag names, trimmed),
 * - blank data rows are skipped; short rows are padded with empty values
 *   instead of failing the whole file.
 *
 * Android ships no CSV library, so this is a small hand-rolled parser. It
 * implements the same quoting dialect the desktop's parser accepts — that
 * dialect, not any particular library, is the shared format.
 */
object CsvParser {

    /** Parse CSV text into (headings, data rows with 1-based indices). */
    fun parse(text: String): Pair<List<String>, List<IndexedRow>> {
        val records = tokenize(text.removePrefix("\uFEFF"))
        if (records.isEmpty()) return emptyList<String>() to emptyList()
        val headings = records.first().map { it.trim() }
        val width = headings.size
        val rows = mutableListOf<IndexedRow>()
        for ((position, record) in records.drop(1).withIndex()) {
            // Row index is the data-row number in the file (1-based), which
            // is what candidate labels and the desktop preview report.
            if (record.all { it.isEmpty() }) continue
            val values = (record + List(width) { "" }).take(width)
            rows += IndexedRow(position + 1, values)
        }
        return headings to rows
    }

    fun parse(stream: InputStream): Pair<List<String>, List<IndexedRow>> =
        stream.bufferedReader(Charsets.UTF_8).use { parse(it.readText()) }

    fun parse(reader: Reader): Pair<List<String>, List<IndexedRow>> =
        parse(reader.readText())

    /**
     * Split raw CSV text into records of fields, honouring quoting.
     * Handles \n, \r\n and lone \r line endings.
     */
    private fun tokenize(text: String): List<List<String>> {
        val records = mutableListOf<List<String>>()
        var record = mutableListOf<String>()
        val field = StringBuilder()
        var inQuotes = false
        var i = 0
        fun endField() {
            record += field.toString()
            field.clear()
        }
        fun endRecord() {
            endField()
            records += record
            record = mutableListOf()
        }
        while (i < text.length) {
            val ch = text[i]
            when {
                inQuotes -> when (ch) {
                    '"' -> if (i + 1 < text.length && text[i + 1] == '"') {
                        field.append('"'); i++
                    } else inQuotes = false
                    else -> field.append(ch)
                }
                ch == '"' && field.isEmpty() -> inQuotes = true
                ch == ',' -> endField()
                ch == '\n' -> endRecord()
                ch == '\r' -> { /* handled with the following \n, or alone below */ }
                else -> field.append(ch)
            }
            // A lone \r (no \n after) also ends a record.
            if (!inQuotes && ch == '\r' && (i + 1 >= text.length || text[i + 1] != '\n')) endRecord()
            i++
        }
        // Trailing record without a final newline. (A trailing empty record
        // left by a final newline is harmless: blank rows are skipped when
        // the records are turned into data rows, and the header is never
        // blank in a real file.)
        if (field.isNotEmpty() || record.isNotEmpty()) endRecord()
        return records
    }
}

/** Minimal CSV writer: quotes fields that contain commas, quotes or newlines. */
object CsvWriter {
    fun escape(value: String): String =
        if (value.any { it == ',' || it == '"' || it == '\n' || it == '\r' }) {
            "\"" + value.replace("\"", "\"\"") + "\""
        } else value

    fun line(values: List<String>): String = values.joinToString(",") { escape(it) }

    fun write(header: List<String>, rows: List<List<String>>): String =
        buildString {
            append(line(header)).append("\r\n")
            for (row in rows) append(line(row)).append("\r\n")
        }
}
