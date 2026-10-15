package com.devxen.mp3csvtagger

import android.app.Activity
import android.graphics.Typeface
import android.os.Bundle
import android.util.TypedValue
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * The built-in Help screen.
 *
 * Renders `assets/help.md` — the same text that ships in the repo's
 * docs/ANDROID_HELP.md, so what users read in the app and what they read
 * on the web cannot drift apart. The renderer is intentionally tiny: it
 * understands `#`/`##` headings, `-` bullets and paragraphs, which is all
 * the help file uses. Keeping a full markdown engine out of the app keeps
 * the APK small and the rendering predictable.
 */
class HelpActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = "MP3 CSV Tagger — Help"

        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(16), dp(20), dp(24))
        }
        val markdown = assets.open("help.md").bufferedReader().readText()
        for (block in markdownToBlocks(markdown)) {
            column.addView(blockView(block))
        }
        setContentView(ScrollView(this).apply { addView(column) })
    }

    private fun dp(value: Int): Int =
        TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value.toFloat(), resources.displayMetrics).toInt()

    /** One rendered block of the help file. */
    private sealed interface Block {
        data class Heading(val level: Int, val text: String) : Block
        data class Bullet(val text: String) : Block
        data class Paragraph(val text: String) : Block
        data object Rule : Block
    }

    /**
     * Split markdown into blocks. Consecutive lines of a paragraph are
     * joined (the file hard-wraps at ~72 columns); bullets keep their lines
     * joined too. `**bold**` and `` `code` `` markers are stripped — the
     * emphasis survives as wording; the raw markers would just be noise.
     */
    private fun markdownToBlocks(markdown: String): List<Block> {
        val blocks = mutableListOf<Block>()
        val pending = StringBuilder()
        fun flush() {
            val text = pending.toString().trim()
            if (text.isNotEmpty()) blocks += Block.Paragraph(clean(text))
            pending.clear()
        }
        for (line in markdown.lines()) {
            val trimmed = line.trim()
            when {
                trimmed.startsWith("## ") -> { flush(); blocks += Block.Heading(2, clean(trimmed.drop(3))) }
                trimmed.startsWith("# ") -> { flush(); blocks += Block.Heading(1, clean(trimmed.drop(2))) }
                trimmed == "---" -> { flush(); blocks += Block.Rule }
                trimmed.startsWith("- ") -> { flush(); blocks += Block.Bullet(clean(trimmed.drop(2))) }
                trimmed.isEmpty() -> flush()
                else -> {
                    if (pending.isNotEmpty()) pending.append(' ')
                    pending.append(trimmed)
                }
            }
        }
        flush()
        return blocks
    }

    private fun clean(text: String): String =
        text.replace("**", "").replace("`", "")

    private fun blockView(block: Block): TextView = when (block) {
        is Block.Heading -> TextView(this).apply {
            text = block.text
            setTypeface(null, Typeface.BOLD)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, if (block.level == 1) 22f else 17f)
            setPadding(0, dp(if (block.level == 1) 4 else 18), 0, dp(6))
        }
        is Block.Bullet -> TextView(this).apply {
            text = "•  ${block.text}"
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            setPadding(dp(10), dp(2), 0, dp(2))
        }
        is Block.Paragraph -> TextView(this).apply {
            text = block.text
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            setPadding(0, dp(2), 0, dp(6))
        }
        Block.Rule -> TextView(this).apply {
            text = "— — —"
            gravity = android.view.Gravity.CENTER
            setPadding(0, dp(8), 0, dp(8))
        }
    }
}
