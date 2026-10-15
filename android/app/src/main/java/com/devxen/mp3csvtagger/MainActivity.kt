package com.devxen.mp3csvtagger

import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.documentfile.provider.DocumentFile
import androidx.lifecycle.lifecycleScope
import com.devxen.mp3csvtagger.engine.CsvLayer
import com.devxen.mp3csvtagger.engine.CsvParser
import com.devxen.mp3csvtagger.engine.CsvSource
import com.devxen.mp3csvtagger.engine.CsvWriter
import com.devxen.mp3csvtagger.engine.FilenamePatternSource
import com.devxen.mp3csvtagger.engine.LayerSource
import com.devxen.mp3csvtagger.engine.Mp3Item
import com.devxen.mp3csvtagger.engine.Preview
import com.devxen.mp3csvtagger.engine.Role
import com.devxen.mp3csvtagger.engine.buildPreview
import com.devxen.mp3csvtagger.engine.exportTagsCsv
import com.devxen.mp3csvtagger.engine.ChangeLog
import com.devxen.mp3csvtagger.tagio.Id3Reader
import com.devxen.mp3csvtagger.tagio.JauTagIO
import com.devxen.mp3csvtagger.tagio.SnapshotEntry
import com.devxen.mp3csvtagger.tagio.TagChange
import com.devxen.mp3csvtagger.tagio.TagSnapshot
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * MP3 CSV Tagger — the whole app in one activity.
 *
 * The flow mirrors the desktop program: pick a music folder, add CSV
 * layers (and/or filename-pattern layers), build a preview, then apply.
 * All heavy work (scanning, preview, writing, undo) runs on the IO
 * dispatcher; the UI only renders state held in this activity.
 *
 * Files are reached exclusively through the Storage Access Framework:
 * the folder and CSV grants the user picks are persisted, so reopening
 * the app picks up where they left off. The app holds no permissions
 * and needs none.
 *
 * Tag writes never edit a document in place (SAF documents are streams):
 * a changed file is copied to a temp file, rewritten there with
 * jaudiotagger, and streamed back — see [applyPreview].
 *
 * Undo is a tag snapshot, not a file backup — see [TagSnapshot].
 */
class MainActivity : ComponentActivity() {

    // ------------------------------------------------------------------
    // State
    // ------------------------------------------------------------------

    /** A scanned MP3: engine data plus everything needed to write it back. */
    private data class ScannedFile(
        val item: Mp3Item,
        val uri: Uri,
        val relativePath: String,
        val size: Long,
        val mtime: Long,
    )

    private var treeUri: Uri? = null
    private var treeName: String = ""
    private val layers = mutableListOf<LayerSource>()
    private var scanned: List<ScannedFile> = emptyList()
    private var scanErrors: List<String> = emptyList()
    private var preview: Preview? = null
    private var busy = false

    // ------------------------------------------------------------------
    // Views (built in code; the layout is a simple vertical flow)
    // ------------------------------------------------------------------

    private lateinit var statusText: TextView
    private lateinit var layersBox: LinearLayout
    private lateinit var progressBar: ProgressBar
    private lateinit var progressText: TextView
    private lateinit var previewBox: LinearLayout
    private lateinit var applyButton: Button

    private val prefs by lazy { getSharedPreferences("state", MODE_PRIVATE) }

    // ------------------------------------------------------------------
    // SAF pickers
    // ------------------------------------------------------------------

    private val pickFolder = registerForActivityResult(
        ActivityResultContracts.OpenDocumentTree()
    ) { uri ->
        if (uri == null) return@registerForActivityResult
        takeGrant(uri)
        treeUri = uri
        treeName = DocumentFile.fromTreeUri(this, uri)?.name ?: "music folder"
        scanned = emptyList()
        preview = null
        saveState()
        renderAll()
        setStatus("Folder picked: $treeName. Add a CSV layer, then Build Preview.")
    }

    private val pickCsv = registerForActivityResult(
        ActivityResultContracts.OpenMultipleDocuments()
    ) { uris ->
        if (uris.isEmpty()) return@registerForActivityResult
        lifecycleScope.launch { addCsvLayers(uris) }
    }

    private var pendingExportText: String? = null
    private val createExport = registerForActivityResult(
        ActivityResultContracts.CreateDocument("text/csv")
    ) { uri ->
        val text = pendingExportText
        pendingExportText = null
        if (uri == null || text == null) return@registerForActivityResult
        lifecycleScope.launch {
            runIo("Writing export…") {
                contentResolver.openOutputStream(uri, "wt")?.use { out ->
                    out.write(text.toByteArray(Charsets.UTF_8))
                }
            }
            setStatus("Tags exported to ${displayName(uri)}.")
        }
    }

    private fun takeGrant(uri: Uri) {
        try {
            contentResolver.takePersistableUriPermission(
                uri,
                Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
            )
        } catch (_: SecurityException) {
            // Some providers hand out read-only or non-persistable grants;
            // the picker result still works for this session.
            try {
                contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            } catch (_: SecurityException) {
            }
        }
    }

    private fun displayName(uri: Uri): String =
        DocumentFile.fromSingleUri(this, uri)?.name ?: uri.lastPathSegment ?: uri.toString()

    // ------------------------------------------------------------------
    // Lifecycle + layout
    // ------------------------------------------------------------------

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildLayout()
        restoreState()
        renderAll()
        if (treeUri == null) {
            setStatus("Start by picking your music folder. New here? Tap Help — it covers the whole workflow.")
        } else {
            setStatus("Folder: $treeName. Add a CSV layer, then Build Preview.")
        }
    }

    private fun dp(value: Int): Int = TypedValue.applyDimension(
        TypedValue.COMPLEX_UNIT_DIP, value.toFloat(), resources.displayMetrics
    ).toInt()

    private fun buildLayout() {
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }

        // Header row: app name + Help.
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(16), dp(12), dp(8), dp(4))
        }
        header.addView(TextView(this).apply {
            text = "MP3 CSV Tagger"
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 20f)
            setTypeface(null, android.graphics.Typeface.BOLD)
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        })
        header.addView(Button(this).apply {
            text = "Help"
            setOnClickListener { startActivity(Intent(this@MainActivity, HelpActivity::class.java)) }
        })
        root.addView(header)

        statusText = TextView(this).apply {
            setPadding(dp(16), dp(2), dp(16), dp(8))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
        }
        root.addView(statusText)

        progressBar = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            visibility = View.GONE
            isIndeterminate = true
        }
        root.addView(progressBar)
        progressText = TextView(this).apply {
            setPadding(dp(16), 0, dp(16), dp(4))
            visibility = View.GONE
        }
        root.addView(progressText)

        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(4), dp(16), dp(24))
        }

        // Source pickers.
        content.addView(buttonRow(
            "Pick music folder" to { pickFolder.launch(null) },
            "Add CSV file" to { pickCsv.launch(arrayOf("text/*", "text/csv", "text/comma-separated-values", "*/*")) },
        ))
        content.addView(buttonRow(
            "Add filename pattern" to { showAddPatternDialog() },
            "Export tags to CSV" to { exportTags() },
        ))

        content.addView(sectionTitle("Layers (run top to bottom)"))
        layersBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        content.addView(layersBox)

        content.addView(buttonRow(
            "Build Preview" to { buildPreviewClicked() },
            "Undo last run" to { undoClicked() },
        ))

        content.addView(sectionTitle("Preview"))
        previewBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        content.addView(previewBox)

        applyButton = Button(this).apply {
            text = "Apply"
            visibility = View.GONE
            setOnClickListener { applyClicked() }
        }
        content.addView(applyButton)

        root.addView(ScrollView(this).apply { addView(content) })
        setContentView(root)
    }

    private fun sectionTitle(text: String) = TextView(this).apply {
        this.text = text
        setTypeface(null, android.graphics.Typeface.BOLD)
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
        setPadding(0, dp(16), 0, dp(6))
    }

    private fun buttonRow(vararg buttons: Pair<String, () -> Unit>): LinearLayout {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, dp(4), 0, dp(4))
        }
        for ((label, action) in buttons) {
            row.addView(Button(this).apply {
                text = label
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                setOnClickListener { action() }
            })
        }
        return row
    }

    // ------------------------------------------------------------------
    // Rendering
    // ------------------------------------------------------------------

    private fun renderAll() {
        renderLayers()
        renderPreview()
    }

    private fun renderLayers() {
        layersBox.removeAllViews()
        if (layers.isEmpty()) {
            layersBox.addView(TextView(this).apply {
                text = "No layers yet. Add a CSV file — one is enough for most jobs — or a filename pattern."
            })
            return
        }
        layers.forEachIndexed { index, layer ->
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(0, dp(2), 0, dp(2))
            }
            row.addView(CheckBox(this).apply {
                isChecked = layer.included
                setOnCheckedChangeListener { _, checked -> setLayerIncluded(index, checked) }
            })
            row.addView(TextView(this).apply {
                text = layer.name
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                setOnClickListener { showLayerDetails(index) }
            })
            row.addView(smallButton("↑") { moveLayer(index, -1) })
            row.addView(smallButton("↓") { moveLayer(index, 1) })
            row.addView(smallButton("✕") { removeLayer(index) })
            layersBox.addView(row)
        }
    }

    private fun smallButton(label: String, action: () -> Unit) = Button(this).apply {
        text = label
        setOnClickListener { action() }
    }

    private fun renderPreview() {
        previewBox.removeAllViews()
        val current = preview
        if (current == null) {
            previewBox.addView(TextView(this).apply { text = "No preview yet." })
            applyButton.visibility = View.GONE
            return
        }
        previewBox.addView(TextView(this).apply {
            text = "Scanned ${current.filesScanned} file(s) · matched ${current.filesMatched} · " +
                "${current.totalChanges} tag change(s)"
            setTypeface(null, android.graphics.Typeface.BOLD)
        })
        for (error in current.scanErrors) {
            previewBox.addView(TextView(this).apply { text = "⚠ $error" })
        }
        for (row in current.rows) {
            previewBox.addView(TextView(this).apply {
                text = row.displayName
                setTypeface(null, android.graphics.Typeface.BOLD)
                setPadding(0, dp(10), 0, 0)
            })
            for ((tagName, cell) in row.cells) {
                val label = buildString {
                    append("$tagName: ")
                    if (cell.oldValue.isEmpty()) append("(empty)") else append(cell.oldValue)
                    append(" → ")
                    append(cell.value)
                    if (cell.hasMultiple) append("  (${cell.candidates.size} values — tap to choose)")
                    if (!cell.changed) append("  (no change)")
                }
                previewBox.addView(TextView(this).apply {
                    text = label
                    setPadding(dp(12), dp(1), 0, dp(1))
                    if (cell.hasMultiple) {
                        setOnClickListener { showCandidateChooser(row.itemId, tagName) }
                    }
                })
            }
        }
        applyButton.visibility = if (current.totalChanges > 0) View.VISIBLE else View.GONE
        applyButton.text = "Apply ${current.totalChanges} change(s)"
    }

    private fun setStatus(message: String) {
        statusText.text = message
    }

    private fun setBusyUI(busyNow: Boolean, message: String = "") {
        busy = busyNow
        progressBar.visibility = if (busyNow) View.VISIBLE else View.GONE
        progressText.visibility = if (busyNow) View.VISIBLE else View.GONE
        if (busyNow) progressText.text = message
    }

    /** Run [block] on the IO dispatcher with the busy indicator up. */
    private suspend fun <T> runIo(message: String, block: () -> T): T {
        setBusyUI(true, message)
        try {
            return withContext(Dispatchers.IO) { block() }
        } finally {
            setBusyUI(false)
        }
    }

    // ------------------------------------------------------------------
    // Layers: add / reorder / include / remove / roles
    // ------------------------------------------------------------------

    private suspend fun addCsvLayers(uris: List<Uri>) {
        for (uri in uris) {
            takeGrant(uri)
            val id = uri.toString()
            if (layers.any { it is CsvSource && it.csv.id == id }) continue
            try {
                val (layer, savedRoles) = runIo("Reading ${displayName(uri)}…") {
                    val (headings, rows) = contentResolver.openInputStream(uri)?.use { CsvParser.parse(it) }
                        ?: throw IllegalStateException("Could not open the file")
                    val csv = CsvLayer(id, displayName(uri), headings, rows)
                    csv to savedRolesFor(id)
                }
                // Roles remembered from a previous session with this file win.
                if (savedRoles != null) {
                    for (tag in layer.tags) savedRoles[tag.name]?.let { tag.role = it }
                }
                layers += CsvSource(layer)
            } catch (e: Exception) {
                showMessage("Could not add CSV", e.message ?: e.toString())
            }
        }
        preview = null
        saveState()
        renderAll()
    }

    private fun setLayerIncluded(index: Int, included: Boolean) {
        when (val layer = layers[index]) {
            is CsvSource -> layer.csv.included = included
            is FilenamePatternSource -> layers[index] = layer.copy(included = included)
        }
        preview = null
        saveState()
        renderPreview()
    }

    private fun moveLayer(index: Int, direction: Int) {
        val target = index + direction
        if (target !in layers.indices) return
        val item = layers.removeAt(index)
        layers.add(target, item)
        preview = null
        saveState()
        renderAll()
    }

    private fun removeLayer(index: Int) {
        layers.removeAt(index)
        preview = null
        saveState()
        renderAll()
    }

    /** Details for a layer: role editor for CSVs, explanation for patterns. */
    private fun showLayerDetails(index: Int) {
        when (val layer = layers[index]) {
            is FilenamePatternSource -> showMessage(
                "Filename pattern",
                "Pattern: ${layer.pattern}\n\nEach {Tag Name} in the pattern captures part of " +
                    "a file's folder path or name and writes it as that tag. Captured columns " +
                    "always have the Write role. See Help → Filename patterns.",
            )
            is CsvSource -> showRolesDialog(layer.csv)
        }
    }

    /** Role editor: one radio row (Match / Write / Skip) per CSV column. */
    private fun showRolesDialog(csv: CsvLayer) {
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(8))
        }
        val groups = mutableListOf<Pair<com.devxen.mp3csvtagger.engine.CsvTag, RadioGroup>>()
        for (tag in csv.tags) {
            column.addView(TextView(this).apply {
                text = tag.name
                setTypeface(null, android.graphics.Typeface.BOLD)
                setPadding(0, dp(10), 0, 0)
            })
            val group = RadioGroup(this).apply { orientation = RadioGroup.HORIZONTAL }
            for (role in Role.entries) {
                group.addView(RadioButton(this).apply {
                    text = role.name
                    id = role.value
                    isChecked = tag.role == role
                })
            }
            groups += tag to group
            column.addView(group)
        }
        AlertDialog.Builder(this)
            .setTitle(csv.name)
            .setView(ScrollView(this).apply { addView(column) })
            .setPositiveButton("Done") { _, _ ->
                for ((tag, group) in groups) {
                    tag.role = Role.fromValue(group.checkedRadioButtonId)
                }
                preview = null
                saveState()
                renderPreview()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showAddPatternDialog() {
        val input = EditText(this).apply {
            hint = "{Artist}/{Album}/{Track} - {Title}"
            setSingleLine(false)
        }
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(0))
            addView(TextView(this@MainActivity).apply {
                text = "Derive tags from folder and file names. Segments are separated by /; " +
                    "{Tag Name} parts capture text, everything else must match literally. " +
                    "The last segment matches the file name (without .mp3)."
            })
            addView(input)
        }
        AlertDialog.Builder(this)
            .setTitle("Add filename pattern")
            .setView(container)
            .setPositiveButton("Add") { _, _ ->
                val pattern = input.text.toString().trim()
                if (pattern.isNotEmpty()) {
                    layers += FilenamePatternSource(pattern)
                    preview = null
                    saveState()
                    renderAll()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    // ------------------------------------------------------------------
    // State persistence (folder grant, layer list, roles, last run)
    // ------------------------------------------------------------------

    private fun saveState() {
        val csvArray = JSONArray()
        for (layer in layers) {
            when (layer) {
                is CsvSource -> {
                    val roles = JSONObject()
                    for (tag in layer.csv.tags) roles.put(tag.name, tag.role.value)
                    csvArray.put(JSONObject().apply {
                        put("type", "csv")
                        put("id", layer.csv.id)
                        put("included", layer.csv.included)
                        put("roles", roles)
                    })
                }
                is FilenamePatternSource -> csvArray.put(JSONObject().apply {
                    put("type", "pattern")
                    put("pattern", layer.pattern)
                    put("included", layer.included)
                })
            }
        }
        prefs.edit()
            .putString("treeUri", treeUri?.toString())
            .putString("treeName", treeName)
            .putString("layers", csvArray.toString())
            .apply()
    }

    private fun savedLayersJson(): JSONArray? =
        prefs.getString("layers", null)?.let { runCatching { JSONArray(it) }.getOrNull() }

    private fun savedRolesFor(csvId: String): Map<String, Role>? {
        val array = savedLayersJson() ?: return null
        for (i in 0 until array.length()) {
            val obj = array.optJSONObject(i) ?: continue
            if (obj.optString("type") == "csv" && obj.optString("id") == csvId) {
                val roles = obj.optJSONObject("roles") ?: return null
                val map = mutableMapOf<String, Role>()
                val keys = roles.keys()
                while (keys.hasNext()) {
                    val key = keys.next()
                    map[key] = Role.fromValue(roles.optInt(key, Role.Skip.value))
                }
                return map
            }
        }
        return null
    }

    private fun restoreState() {
        treeUri = prefs.getString("treeUri", null)?.let { Uri.parse(it) }
        treeName = prefs.getString("treeName", "") ?: ""
        val array = savedLayersJson() ?: return
        // The saved list mixes CSV layers and pattern layers in run order.
        // Patterns need no loading; CSVs must be re-read (their grants
        // persist), after which the combined list is rebuilt in the exact
        // saved order.
        data class SavedEntry(val type: String, val csvId: String, val pattern: String, val included: Boolean)
        val saved = mutableListOf<SavedEntry>()
        for (i in 0 until array.length()) {
            val obj = array.optJSONObject(i) ?: continue
            saved += SavedEntry(
                type = obj.optString("type"),
                csvId = obj.optString("id"),
                pattern = obj.optString("pattern"),
                included = obj.optBoolean("included", true),
            )
        }
        val csvUris = saved.filter { it.type == "csv" }.map { Uri.parse(it.csvId) }
        if (csvUris.isEmpty()) {
            for (entry in saved) {
                if (entry.type == "pattern") {
                    layers += FilenamePatternSource(entry.pattern, entry.included)
                }
            }
            renderAll()
            return
        }
        lifecycleScope.launch {
            addCsvLayers(csvUris)
            val rebuilt = mutableListOf<LayerSource>()
            for (entry in saved) {
                when (entry.type) {
                    "csv" -> layers.filterIsInstance<CsvSource>()
                        .firstOrNull { it.csv.id == entry.csvId }
                        ?.let { source ->
                            source.csv.included = entry.included
                            rebuilt += source
                        }
                    "pattern" -> rebuilt += FilenamePatternSource(entry.pattern, entry.included)
                }
            }
            layers.clear()
            layers.addAll(rebuilt)
            renderAll()
        }
    }

    // ------------------------------------------------------------------
    // Scanning
    // ------------------------------------------------------------------

    /**
     * Walk the picked folder and read every MP3's tags. Reading pulls only
     * the tag block at the start of each file (see [Id3Reader]); files the
     * stream reader cannot handle fall back to a jaudiotagger read of a
     * temp copy, one file at a time.
     */
    private suspend fun scanFolder(): List<ScannedFile> {
        val uri = treeUri ?: return emptyList()
        return runIo("Scanning $treeName…") {
            val root = DocumentFile.fromTreeUri(this@MainActivity, uri)
                ?: throw IllegalStateException("The picked folder is no longer available — pick it again.")
            val docs = mutableListOf<Pair<DocumentFile, String>>()
            fun walk(dir: DocumentFile, prefix: String) {
                for (child in dir.listFiles()) {
                    val childPath = if (prefix.isEmpty()) child.name ?: "" else "$prefix/${child.name}"
                    when {
                        child.isDirectory -> walk(child, childPath)
                        child.isFile && (child.name?.lowercase()?.endsWith(".mp3") == true) ->
                            docs += child to childPath
                    }
                }
            }
            walk(root, "")
            val errors = mutableListOf<String>()
            val result = docs.map { (doc, relativePath) ->
                val tags = try {
                    contentResolver.openInputStream(doc.uri)?.use { Id3Reader.readTags(it) }
                        ?: throw IllegalStateException("Could not open file")
                } catch (e: Exception) {
                    // Fallback: temp copy + jaudiotagger. A failure here too
                    // means the file is unreadable; report it, don't stop.
                    try {
                        readTagsViaTempCopy(doc.uri)
                    } catch (e2: Exception) {
                        errors += "${doc.name}: ${e2.message ?: "unreadable"}"
                        emptyMap()
                    }
                }
                ScannedFile(
                    item = Mp3Item(doc.uri.toString(), doc.name ?: relativePath, tags),
                    uri = doc.uri,
                    relativePath = relativePath,
                    size = doc.length(),
                    mtime = doc.lastModified(),
                )
            }
            scanErrors = errors
            result
        }
    }

    /** Read tags by copying one document to a temp file for jaudiotagger. */
    private fun readTagsViaTempCopy(uri: Uri): Map<String, String> {
        val temp = File.createTempFile("mp3tagger-read", ".mp3", cacheDir)
        try {
            contentResolver.openInputStream(uri)?.use { input ->
                temp.outputStream().use { input.copyTo(it) }
            } ?: throw IllegalStateException("Could not open file")
            return JauTagIO.readTags(temp)
        } finally {
            temp.delete()
        }
    }

    // ------------------------------------------------------------------
    // Preview
    // ------------------------------------------------------------------

    private fun buildPreviewClicked() {
        if (busy) return
        if (treeUri == null) {
            showMessage("No folder", "Pick your music folder first.")
            return
        }
        if (layers.none { it.included }) {
            showMessage("No layers", "Add a CSV file or a filename pattern, and make sure it is ticked on.")
            return
        }
        lifecycleScope.launch {
            if (scanned.isEmpty()) scanned = scanFolder()
            preview = withContext(Dispatchers.Default) {
                buildPreview(
                    layers = layers,
                    files = scanned.map { it.item },
                    scanErrors = scanErrors,
                    relativePaths = scanned.associate { it.item.id to it.relativePath },
                )
            }
            renderPreview()
            setStatus(
                "Preview built: ${preview?.filesMatched ?: 0} file(s) matched, " +
                    "${preview?.totalChanges ?: 0} change(s). Review, then Apply.",
            )
        }
    }

    /** Let the user pick among a cell's candidate values. */
    private fun showCandidateChooser(itemId: String, tagName: String) {
        val current = preview ?: return
        val cell = current.rowForItem(itemId)?.cells?.get(tagName) ?: return
        val labels = cell.candidates.map { candidate ->
            val origin = if (candidate.sourceRow > 0) {
                "${candidate.sourceName} · row ${candidate.sourceRow}"
            } else {
                candidate.sourceName
            }
            (if (candidate.value.isEmpty()) "(empty)" else candidate.value) + "   —  " + origin
        }.toTypedArray()
        AlertDialog.Builder(this)
            .setTitle("$tagName — choose a value")
            .setSingleChoiceItems(labels, cell.selected) { dialog, which ->
                cell.selected = which
                dialog.dismiss()
                renderPreview()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    // ------------------------------------------------------------------
    // Apply + tag-snapshot undo
    // ------------------------------------------------------------------

    private fun applyClicked() {
        val current = preview ?: return
        if (current.totalChanges == 0) return
        AlertDialog.Builder(this)
            .setTitle("Apply changes?")
            .setMessage(
                "Write ${current.totalChanges} tag change(s) in ${current.rows.count { it.changeCount > 0 }} file(s)?\n\n" +
                    "A change log and a tag snapshot (for undo) are saved first. " +
                    "Undo restores tags only — no file copies are made.",
            )
            .setPositiveButton("Apply") { _, _ ->
                lifecycleScope.launch { applyPreview(current) }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    /**
     * Write the preview's selected values.
     *
     * Order matters:
     * 1. Snapshot every file that will change (tags only) and keep the
     *    entries in memory until the run folder is written.
     * 2. Write the change log + snapshot into the run folder FIRST, so an
     *    interrupted run still leaves its undo data behind.
     * 3. Then write each file once: temp copy → jaudiotagger → stream back.
     */
    private suspend fun applyPreview(current: Preview) {
        val byId = scanned.associateBy { it.item.id }
        val changedRows = current.rows.filter { it.changeCount > 0 }
        val runStamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        val logStamp = SimpleDateFormat("yyyy/MM/dd HH:mm:ss", Locale.US).format(Date())
        val runFolder = File(
            getExternalFilesDir(null) ?: filesDir, "runs/$runStamp",
        )

        var filesWritten = 0
        var tagsWritten = 0
        val errors = mutableListOf<String>()
        val logRows = mutableListOf<List<String>>()

        runIo("Applying…") {
            runFolder.mkdirs()
            // 1) Snapshots, captured before anything is modified.
            val snapshots = changedRows.mapNotNull { row ->
                val file = byId[row.itemId] ?: return@mapNotNull null
                try {
                    val block = try {
                        contentResolver.openInputStream(file.uri)?.use { Id3Reader.readRawBlock(it) }
                    } catch (e: Exception) {
                        // Unusual headers: keep the whole original block
                        // verbatim rather than skipping the snapshot.
                        contentResolver.openInputStream(file.uri)?.use { Id3Reader.readRawBlockVerbatim(it) }
                    }
                    SnapshotEntry(file.item.id, file.item.displayName, file.size, file.mtime, block)
                } catch (e: Exception) {
                    errors += "${file.item.displayName}: snapshot failed (${e.message})"
                    null
                }
            }
            // 2) Undo data + change log land on disk before any MP3 changes.
            File(runFolder, "undo.snapshot").outputStream().use { TagSnapshot.write(snapshots, it) }

            // 3) Writes.
            for (row in changedRows) {
                val file = byId[row.itemId] ?: continue
                val changes = row.cells.values.filter { it.changed }.map { cell ->
                    TagChange(cell.frame, cell.tagName, cell.value)
                }
                if (changes.isEmpty()) continue
                try {
                    writeOneFile(file.uri, changes)
                    filesWritten++
                    for (cell in row.cells.values.filter { it.changed }) {
                        logRows += ChangeLog.row(
                            logStamp, file.item.displayName, cell.tagName,
                            cell.frame, cell.oldValue, cell.value,
                        )
                        tagsWritten++
                    }
                } catch (e: Exception) {
                    errors += "${file.item.displayName}: ${e.message ?: "write failed"}"
                }
            }
            val logFile = File(runFolder, "mp3tag_$runStamp.log.csv")
            logFile.writeText(
                CsvWriter.write(ChangeLog.headers, logRows), Charsets.UTF_8,
            )
        }

        prefs.edit().putString("lastRunFolder", runFolder.absolutePath).apply()
        // Tags on disk have changed; the next preview must re-scan.
        scanned = emptyList()
        preview = null
        renderPreview()
        val message = buildString {
            append("Wrote $tagsWritten tag(s) in $filesWritten file(s).")
            if (errors.isNotEmpty()) {
                append("\n\nProblems:\n")
                errors.take(10).forEach { append("• $it\n") }
            }
            append("\nChange log + undo snapshot:\n${runFolder.absolutePath}")
        }
        showMessage("Apply finished", message)
        setStatus("Applied $tagsWritten tag(s). Undo is available from \"Undo last run\".")
    }

    /** Rewrite one document's tags via a temp file + jaudiotagger. */
    private fun writeOneFile(uri: Uri, changes: List<TagChange>) {
        val temp = File.createTempFile("mp3tagger-write", ".mp3", cacheDir)
        try {
            contentResolver.openInputStream(uri)?.use { input ->
                temp.outputStream().use { input.copyTo(it) }
            } ?: throw IllegalStateException("Could not open file for writing")
            JauTagIO.writeTags(temp, changes)
            contentResolver.openOutputStream(uri, "wt")?.use { out ->
                temp.inputStream().use { it.copyTo(out) }
            } ?: throw IllegalStateException("Could not write file back")
        } finally {
            temp.delete()
        }
    }

    // ------------------------------------------------------------------
    // Undo
    // ------------------------------------------------------------------

    private fun undoClicked() {
        val folderPath = prefs.getString("lastRunFolder", null)
        if (folderPath == null) {
            showMessage("Undo", "No run to undo yet. Undo becomes available after an Apply.")
            return
        }
        lifecycleScope.launch {
            val entries = runIo("Reading undo snapshot…") {
                val file = File(folderPath, "undo.snapshot")
                if (!file.exists()) throw IllegalStateException("The last run's undo file is missing.")
                file.inputStream().use { TagSnapshot.read(it) }
            }
            AlertDialog.Builder(this@MainActivity)
                .setTitle("Undo last run?")
                .setMessage(
                    "Restore the tags of ${entries.size} file(s) from the tag snapshot?\n\n" +
                        "Only tags are restored; audio is never touched. Files that changed " +
                        "since the run are skipped with a warning.",
                )
                .setPositiveButton("Undo") { _, _ ->
                    lifecycleScope.launch { performUndo(entries, force = false) }
                }
                .setNegativeButton("Cancel", null)
                .show()
        }
    }

    private suspend fun performUndo(entries: List<SnapshotEntry>, force: Boolean) {
        var restored = 0
        val skipped = mutableListOf<SnapshotEntry>()
        val errors = mutableListOf<String>()
        runIo("Restoring tags…") {
            for (entry in entries) {
                val uri = Uri.parse(entry.itemId)
                val doc = DocumentFile.fromSingleUri(this@MainActivity, uri)
                if (doc == null || !doc.exists()) {
                    errors += "${entry.displayName}: file not found"
                    continue
                }
                if (!force && !TagSnapshot.unchanged(entry, doc.length(), doc.lastModified())) {
                    skipped += entry
                    continue
                }
                try {
                    contentResolver.openOutputStream(uri, "wt")?.use { out ->
                        TagSnapshot.restore(entry, { contentResolver.openInputStream(uri)!! }, out)
                    } ?: throw IllegalStateException("Could not open file for writing")
                    restored++
                } catch (e: Exception) {
                    errors += "${entry.displayName}: ${e.message ?: "restore failed"}"
                }
            }
        }
        scanned = emptyList()
        preview = null
        renderPreview()
        val message = buildString {
            append("Restored tags on $restored file(s).")
            if (skipped.isNotEmpty()) append("\nSkipped (changed since the run): ${skipped.joinToString { it.displayName }}")
            if (errors.isNotEmpty()) {
                append("\n\nProblems:\n")
                errors.take(10).forEach { append("• $it\n") }
            }
        }
        // Offer a forced pass for exactly the skipped files.
        if (skipped.isNotEmpty() && !force) {
            AlertDialog.Builder(this)
                .setTitle("Some files were skipped")
                .setMessage(message + "\n\nForce-restore the skipped files anyway? Only do this if you know their audio has not been replaced.")
                .setPositiveButton("Force restore") { _, _ ->
                    lifecycleScope.launch { performUndo(skipped, force = true) }
                }
                .setNegativeButton("Leave them", null)
                .show()
        } else {
            showMessage("Undo finished", message)
        }
        setStatus("Undo finished: $restored file(s) restored.")
    }

    // ------------------------------------------------------------------
    // Export
    // ------------------------------------------------------------------

    private fun exportTags() {
        if (treeUri == null) {
            showMessage("Export tags", "Pick your music folder first.")
            return
        }
        lifecycleScope.launch {
            if (scanned.isEmpty()) scanned = scanFolder()
            pendingExportText = exportTagsCsv(scanned.map { it.item })
            createExport.launch("mp3-tags.csv")
        }
    }

    // ------------------------------------------------------------------
    // Small helpers
    // ------------------------------------------------------------------

    private fun showMessage(title: String, message: String) {
        AlertDialog.Builder(this)
            .setTitle(title)
            .setMessage(message)
            .setPositiveButton("OK", null)
            .show()
    }
}
