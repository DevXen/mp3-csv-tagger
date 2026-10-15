package com.devxen.mp3csvtagger

import android.app.AlertDialog
import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.net.Uri
import android.os.Bundle
import android.os.Parcelable
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
import androidx.core.content.pm.ShortcutInfoCompat
import androidx.core.content.pm.ShortcutManagerCompat
import androidx.core.graphics.drawable.IconCompat
import androidx.documentfile.provider.DocumentFile
import androidx.lifecycle.lifecycleScope
import com.devxen.mp3csvtagger.engine.COVER_PRESENT
import com.devxen.mp3csvtagger.engine.COVER_TAG_NAME
import com.devxen.mp3csvtagger.engine.Cell
import com.devxen.mp3csvtagger.engine.CsvLayer
import com.devxen.mp3csvtagger.engine.CsvParser
import com.devxen.mp3csvtagger.engine.CsvSource
import com.devxen.mp3csvtagger.engine.CsvWriter
import com.devxen.mp3csvtagger.engine.FilenamePatternSource
import com.devxen.mp3csvtagger.engine.Job
import com.devxen.mp3csvtagger.engine.JobCsvLayer
import com.devxen.mp3csvtagger.engine.JobLayer
import com.devxen.mp3csvtagger.engine.JobPatternLayer
import com.devxen.mp3csvtagger.engine.LayerSource
import com.devxen.mp3csvtagger.engine.Mp3Item
import com.devxen.mp3csvtagger.engine.Preview
import com.devxen.mp3csvtagger.engine.PreviewRow
import com.devxen.mp3csvtagger.engine.Role
import com.devxen.mp3csvtagger.engine.SYNC_SOURCE_NAME
import com.devxen.mp3csvtagger.engine.ValuesSource
import com.devxen.mp3csvtagger.engine.albumCompleteness
import com.devxen.mp3csvtagger.engine.buildPreview
import com.devxen.mp3csvtagger.engine.buildSyncValues
import com.devxen.mp3csvtagger.engine.appendTagsCsv
import com.devxen.mp3csvtagger.engine.checkConsistency
import com.devxen.mp3csvtagger.engine.coverTokenSourceId
import com.devxen.mp3csvtagger.engine.defaultSyncTags
import com.devxen.mp3csvtagger.engine.duplicateGroups
import com.devxen.mp3csvtagger.engine.exportTagsCsv
import com.devxen.mp3csvtagger.engine.pairLibraries
import com.devxen.mp3csvtagger.engine.renderCompletenessText
import com.devxen.mp3csvtagger.engine.variantGroups
import com.devxen.mp3csvtagger.engine.ChangeLog
import com.devxen.mp3csvtagger.tagio.CoverArtwork
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
 *
 * Round 2 additions, all built on the same scan/preview/apply machinery:
 * tappable preview cells with hand-typed manual edits, group-by-album
 * preview, tag sync from a second folder (including cover art, resolved
 * from the source file at apply time), read-only consistency and library
 * reports, named jobs (with launcher shortcuts), and CSV files arriving
 * through Open-with / the share sheet.
 */
class MainActivity : ComponentActivity() {

    companion object {
        /** Intent action of the dynamic job shortcuts (see the jobs section). */
        const val ACTION_RUN_JOB = "com.devxen.mp3csvtagger.RUN_JOB"

        /** String extra carrying the job name on an [ACTION_RUN_JOB] intent. */
        const val EXTRA_JOB_NAME = "job_name"
    }

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

    /**
     * The SOURCE library's scanned files from the latest tag-sync run,
     * by item id. A sync preview's cover-art cells carry only an opaque
     * token naming the source file (see the engine's Sync.kt); the bytes
     * are read from these files lazily at apply time, so the scan is
     * kept here until then. Text sync values need nothing from it.
     */
    private var syncSourceById: Map<String, ScannedFile> = emptyMap()

    /** Group-by-album preview state (display only; the preview is untouched). */
    private var groupByAlbum = false
    private val collapsedAlbums = mutableSetOf<String>()

    /**
     * Work handed over by the launching intent, done once state restore
     * has finished: a job to run and/or a CSV that arrived through
     * Open-with or the share sheet. Restore rebuilds the layer list
     * asynchronously, so acting on the intent before it completes could
     * have the restore's rebuild wipe out (or duplicate) the intent's
     * layer — the intent waits here instead. See [afterRestore].
     */
    private var pendingJobName: String? = null
    private var pendingImportUri: Uri? = null

    // ------------------------------------------------------------------
    // Views (built in code; the layout is a simple vertical flow)
    // ------------------------------------------------------------------

    private lateinit var statusText: TextView
    private lateinit var layersBox: LinearLayout
    private lateinit var progressBar: ProgressBar
    private lateinit var progressText: TextView
    private lateinit var previewBox: LinearLayout
    private lateinit var applyButton: Button
    private lateinit var groupByAlbumCheck: CheckBox

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

    // Tag sync's source folder: a second, separate tree that is scanned
    // read-only and never becomes the app's working folder.
    private val pickSyncTree = registerForActivityResult(
        ActivityResultContracts.OpenDocumentTree()
    ) { uri ->
        if (uri == null) return@registerForActivityResult
        // Read-only is all a sync source ever needs — it is never written.
        try {
            contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } catch (_: SecurityException) {
            // Non-persistable grant: still usable for this session's scan.
        }
        lifecycleScope.launch { startSyncWith(uri) }
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

    // Append export: the user picks the library CSV to merge into.
    // The merge runs against the current scan and the merged text is
    // written back over the same document, then a summary is shown.
    private val openAppendTarget = registerForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri == null) return@registerForActivityResult
        lifecycleScope.launch { appendExportTo(uri) }
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
        // Before restoring: an intent that launched the app (a job
        // shortcut, an Open-with / shared CSV) is recorded now and acted
        // on when restore finishes — see pendingJobName/pendingImportUri.
        captureLaunchIntent(intent)
        restoreState()
        renderAll()
        if (treeUri == null) {
            setStatus("Start by picking your music folder. New here? Tap Help — it covers the whole workflow.")
        } else {
            setStatus("Folder: $treeName. Add a CSV layer, then Build Preview.")
        }
    }

    /**
     * New intents while the app is already running (the activity is
     * singleTop): a job shortcut tap or another shared CSV. State is
     * already restored in this case, so the intent can be acted on
     * straight away.
     */
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        captureLaunchIntent(intent)
        handlePendingIntent()
    }

    /**
     * Pick the actionable parts out of an incoming intent: an
     * [ACTION_RUN_JOB] action's job name, and a CSV document arriving as
     * a VIEW data URI or a SEND stream extra. Anything else (the plain
     * launcher intent) records nothing.
     */
    private fun captureLaunchIntent(intent: Intent?) {
        if (intent == null) return
        if (intent.action == ACTION_RUN_JOB) {
            intent.getStringExtra(EXTRA_JOB_NAME)?.let { pendingJobName = it }
        }
        when (intent.action) {
            Intent.ACTION_VIEW -> intent.data?.let { pendingImportUri = it }
            Intent.ACTION_SEND -> {
                @Suppress("DEPRECATION")
                (intent.getParcelableExtra<Parcelable>(Intent.EXTRA_STREAM) as? Uri)
                    ?.let { pendingImportUri = it }
            }
        }
    }

    /** Called when state restore has fully rebuilt the layer list. */
    private fun afterRestore() {
        handlePendingIntent()
    }

    /** Act on whatever [captureLaunchIntent] recorded, exactly once each. */
    private fun handlePendingIntent() {
        val jobName = pendingJobName
        val importUri = pendingImportUri
        if (jobName == null && importUri == null) return
        pendingJobName = null
        pendingImportUri = null
        lifecycleScope.launch {
            if (importUri != null) importSharedCsv(importUri)
            if (jobName != null) {
                val job = loadSavedJobs().firstOrNull { it.name == jobName }
                if (job == null) {
                    showMessage("Job not found", "The saved job \"$jobName\" no longer exists.")
                } else {
                    runJob(job)
                }
            }
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

        // Round 2 tools. Sync produces an ordinary preview (applied and
        // undone the usual way); the two reports are strictly read-only.
        content.addView(buttonRow(
            "Sync tags from another folder…" to { syncClicked() },
            "Consistency check…" to { consistencyClicked() },
        ))
        content.addView(buttonRow(
            "Library report…" to { libraryReportClicked() },
        ))

        content.addView(sectionTitle("Jobs"))
        content.addView(buttonRow(
            "Save current job…" to { saveJobClicked() },
            "Jobs…" to { showJobsDialog() },
        ))

        content.addView(sectionTitle("Preview"))
        groupByAlbumCheck = CheckBox(this).apply {
            text = "Group by album"
            setOnCheckedChangeListener { _, checked ->
                groupByAlbum = checked
                renderPreview()
            }
        }
        content.addView(groupByAlbumCheck)
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
        if (groupByAlbum) {
            // Rows grouped under collapsible album headers. Grouping is
            // a display concern only: the Preview object (and Apply)
            // keeps its own flat row order either way.
            val groups = LinkedHashMap<String, MutableList<PreviewRow>>()
            for (row in current.rows) groups.getOrPut(albumOf(row)) { mutableListOf() } += row
            for ((album, rows) in groups) {
                val collapsed = album in collapsedAlbums
                val changes = rows.sumOf { it.changeCount }
                previewBox.addView(TextView(this).apply {
                    text = "${if (collapsed) "▸" else "▾"} $album (${rows.size} file(s), $changes change(s))"
                    setTypeface(null, android.graphics.Typeface.BOLD)
                    setPadding(0, dp(12), 0, dp(2))
                    setOnClickListener {
                        if (collapsed) collapsedAlbums.remove(album) else collapsedAlbums += album
                        renderPreview()
                    }
                })
                if (!collapsed) rows.forEach { renderPreviewRow(it) }
            }
        } else {
            for (row in current.rows) renderPreviewRow(row)
        }
        applyButton.visibility = if (current.totalChanges > 0) View.VISIBLE else View.GONE
        applyButton.text = "Apply ${current.totalChanges} change(s)"
    }

    /**
     * The album a preview row belongs to, for group-by-album: the
     * row's Album value (the value the preview would write, falling
     * back to the file's stored album), then the top folder of the
     * file's relative path, then a plain placeholder for a file at the
     * library root with no album tag at all.
     */
    private fun albumOf(row: PreviewRow): String {
        val cellAlbum = row.cells.entries
            .firstOrNull { (tagName, _) -> tagName.equals("Album", ignoreCase = true) }
            ?.value?.let { if (it.value.isNotEmpty()) it.value else it.oldValue }
        if (!cellAlbum.isNullOrEmpty()) return cellAlbum
        val item = scanned.firstOrNull { it.item.id == row.itemId }?.item
        val tagAlbum = item?.valueFor("Album", "TALB")
        if (!tagAlbum.isNullOrEmpty()) return tagAlbum
        val relativePath = scanned.firstOrNull { it.item.id == row.itemId }?.relativePath ?: ""
        val topFolder = relativePath.substringBefore('/', missingDelimiterValue = "")
        return topFolder.ifEmpty { "(no album)" }
    }

    /** One file's block in the preview: a header row plus its tag cells. */
    private fun renderPreviewRow(row: PreviewRow) {
        // Header row: file name plus a play button. Playing hands the
        // document URI to the system's audio players read-only — the
        // file is opened, never written, by this app.
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(10), 0, 0)
        }
        header.addView(TextView(this).apply {
            text = row.displayName
            setTypeface(null, android.graphics.Typeface.BOLD)
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            setOnLongClickListener { playFile(row.itemId); true }
        })
        header.addView(smallButton("▶") { playFile(row.itemId) })
        previewBox.addView(header)

        for ((tagName, cell) in row.cells) {
            val selectedManual = cell.candidates.getOrNull(cell.selected)?.manual == true
            val label = buildString {
                append("$tagName: ")
                if (cell.oldValue.isEmpty()) append("(empty)") else append(displayValueOf(cell, cell.oldValue))
                append(" → ")
                append(displayValueOf(cell, cell.value))
                if (cell.hasMultiple) append("  (${cell.candidates.size} values — tap to choose)")
                if (!cell.changed) append("  (no change)")
                if (selectedManual) append("  ✎ manual edit")
            }
            previewBox.addView(TextView(this).apply {
                text = label
                setPadding(dp(12), dp(1), 0, dp(1))
                // A hand-typed value is drawn bold so manual edits stand
                // out from layer-produced values at a glance.
                if (selectedManual) setTypeface(null, android.graphics.Typeface.BOLD)
                // Every cell is tappable: the dialog offers the candidate
                // list, a hand edit, and (when one exists) a revert.
                setOnClickListener { showCellDialog(row.itemId, tagName) }
            })
        }
    }

    /**
     * How a cell value is shown. Cover-art cells carry an opaque sync
     * token instead of text (see the engine's Sync.kt) — the user sees
     * the presence marker, never the token.
     */
    private fun displayValueOf(cell: Cell, value: String): String =
        if (cell.frame == "APIC" && value.isNotEmpty()) COVER_PRESENT else value

    /** Play a scanned file in the system's audio player (read-only). */
    private fun playFile(itemId: String) {
        val file = scanned.firstOrNull { it.item.id == itemId } ?: return
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(file.uri, "audio/*")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        try {
            startActivity(Intent.createChooser(intent, "Play ${file.item.displayName}"))
        } catch (e: ActivityNotFoundException) {
            showMessage("Play", "No audio player app is available to play this file.")
        }
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
            loadCsvSource(uri)?.let { layers += it }
        }
        preview = null
        saveState()
        renderAll()
    }

    /**
     * Load one CSV document as a layer source, or return null (after
     * telling the user) when it cannot be read or is already loaded.
     *
     * The URI may be a SAF document URI from a picker, or a file:// URI
     * for a share-sheet import copied into app-private storage — the
     * content resolver opens both, and the copy is what lets an imported
     * layer survive restarts without any grant at all.
     */
    private suspend fun loadCsvSource(uri: Uri): CsvSource? {
        takeGrant(uri)
        val id = uri.toString()
        if (layers.any { it is CsvSource && it.csv.id == id }) return null
        return try {
            val (layer, savedRoles) = runIo("Reading ${displayName(uri)}…") {
                val (headings, rows) = contentResolver.openInputStream(Uri.parse(id))?.use { CsvParser.parse(it) }
                    ?: throw IllegalStateException("Could not open the file")
                val csv = CsvLayer(id, displayName(uri), headings, rows)
                csv to savedRolesFor(id)
            }
            // Roles remembered from a previous session with this file win.
            if (savedRoles != null) {
                for (tag in layer.tags) savedRoles[tag.name]?.let { tag.role = it }
            }
            CsvSource(layer)
        } catch (e: Exception) {
            showMessage("Could not add CSV", e.message ?: e.toString())
            null
        }
    }

    private fun setLayerIncluded(index: Int, included: Boolean) {
        when (val layer = layers[index]) {
            is CsvSource -> layer.csv.included = included
            is FilenamePatternSource -> layers[index] = layer.copy(included = included)
            is ValuesSource -> layers[index] = layer.copy(included = included)
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
            is ValuesSource -> showMessage(
                layer.name,
                "These values were computed by another feature (tag sync) and are applied " +
                    "through the normal preview, change log and undo, like any other layer. " +
                    "The layer itself is not saved: re-run the feature to rebuild it.",
            )
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
                // A values layer (tag sync) holds values computed from a
                // scan of another folder; it cannot be reloaded from
                // saved state, so it is deliberately not persisted.
                is ValuesSource -> Unit
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
        val array = savedLayersJson() ?: run {
            // Nothing saved: restore is trivially complete, so any work
            // the launching intent handed over can start now.
            afterRestore()
            return
        }
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
            afterRestore()
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
            afterRestore()
        }
    }

    // ------------------------------------------------------------------
    // Scanning
    // ------------------------------------------------------------------

    /** The outcome of scanning one folder tree: its files plus per-file errors. */
    private data class ScanOutcome(
        val files: List<ScannedFile>,
        val errors: List<String>,
    )

    /**
     * Walk the picked folder and read every MP3's tags. Reading pulls only
     * the tag block at the start of each file (see [Id3Reader]); files the
     * stream reader cannot handle fall back to a jaudiotagger read of a
     * temp copy, one file at a time.
     */
    private suspend fun scanFolder(): List<ScannedFile> {
        val uri = treeUri ?: return emptyList()
        val outcome = scanTree(uri, treeName)
        scanErrors = outcome.errors
        return outcome.files
    }

    /**
     * Scan ANY folder tree (the working folder, or tag sync's source
     * folder) the same way: walk it, read each MP3's text tags AND cover
     * presence in one pass ([Id3Reader.readScan] — presence only, the
     * image bytes are never loaded by a scan), and report unreadable
     * files as errors instead of stopping. This function touches no
     * activity state, so a sync source scan cannot disturb the working
     * folder's scan or its error list.
     */
    private suspend fun scanTree(tree: Uri, label: String): ScanOutcome {
        return runIo("Scanning $label…") {
            val root = DocumentFile.fromTreeUri(this@MainActivity, tree)
                ?: throw IllegalStateException("The folder is no longer available — pick it again.")
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
                val scan = try {
                    contentResolver.openInputStream(doc.uri)?.use { Id3Reader.readScan(it) }
                        ?: throw IllegalStateException("Could not open file")
                } catch (e: Exception) {
                    // Fallback: temp copy + jaudiotagger. A failure here too
                    // means the file is unreadable; report it, don't stop.
                    try {
                        readScanViaTempCopy(doc.uri)
                    } catch (e2: Exception) {
                        errors += "${doc.name}: ${e2.message ?: "unreadable"}"
                        Id3Reader.TagScan(emptyMap(), hasCover = false)
                    }
                }
                ScannedFile(
                    item = Mp3Item(
                        doc.uri.toString(), doc.name ?: relativePath, scan.tags,
                        hasCover = scan.hasCover,
                    ),
                    uri = doc.uri,
                    relativePath = relativePath,
                    size = doc.length(),
                    mtime = doc.lastModified(),
                )
            }
            ScanOutcome(result, errors)
        }
    }

    /** Read tags by copying one document to a temp file for jaudiotagger. */
    private fun readTagsViaTempCopy(uri: Uri): Map<String, String> =
        readScanViaTempCopy(uri).tags

    /** The [readTagsViaTempCopy] fallback, also reporting cover presence. */
    private fun readScanViaTempCopy(uri: Uri): Id3Reader.TagScan {
        val temp = File.createTempFile("mp3tagger-read", ".mp3", cacheDir)
        try {
            contentResolver.openInputStream(uri)?.use { input ->
                temp.outputStream().use { input.copyTo(it) }
            } ?: throw IllegalStateException("Could not open file")
            return Id3Reader.TagScan(JauTagIO.readTags(temp), JauTagIO.hasArtwork(temp))
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
            (if (candidate.value.isEmpty()) "(empty)" else displayValueOf(cell, candidate.value)) +
                "   —  " + origin
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

    /**
     * The per-cell dialog behind every tappable preview cell: the
     * candidate list (when a cell has several values), a hand edit, and
     * a revert for an existing hand edit.
     *
     * A hand edit is recorded through [Cell.setManualEdit], which makes
     * it an ordinary selected candidate — Apply, the change log and
     * snapshot undo all treat it like any other value, with its source
     * recorded as "manual edit". Typing back exactly the value already
     * selected is a no-op rather than a pointless manual candidate.
     *
     * Cover-art cells are the exception: their "value" is a reference
     * to another file's artwork, not text, so there is nothing to type —
     * the dialog explains where the art comes from and offers only the
     * candidate choice (when there is one).
     */
    private fun showCellDialog(itemId: String, tagName: String) {
        val current = preview ?: return
        val row = current.rowForItem(itemId) ?: return
        val cell = row.cells[tagName] ?: return

        if (cell.frame == "APIC") {
            val builder = AlertDialog.Builder(this)
                .setTitle(tagName)
                .setMessage(
                    "Cover art is an image, not text, so it cannot be typed in.\n\n" +
                        "This change copies the cover from the matching file in the sync " +
                        "source folder when you Apply. The file it comes from is read at " +
                        "that moment; nothing is copied now.",
                )
                .setNegativeButton("Cancel", null)
            if (cell.hasMultiple) {
                builder.setPositiveButton("Choose value…") { _, _ ->
                    showCandidateChooser(itemId, tagName)
                }
            } else {
                builder.setPositiveButton("OK", null)
            }
            builder.show()
            return
        }

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(0))
        }
        container.addView(TextView(this).apply {
            text = "Now: ${if (cell.oldValue.isEmpty()) "(empty)" else cell.oldValue}\n" +
                "Will write: ${if (cell.value.isEmpty()) "(empty)" else cell.value}"
        })
        val input = EditText(this).apply {
            setText(cell.value)
            setSelection(text.length)
            hint = "Type a value to use instead"
        }
        container.addView(input)

        val builder = AlertDialog.Builder(this)
            .setTitle(tagName)
            .setView(container)
            .setPositiveButton("Save edit") { _, _ ->
                val typed = input.text.toString()
                if (typed != cell.value) {
                    cell.setManualEdit(typed)
                    renderPreview()
                }
            }
            .setNegativeButton("Cancel", null)
        val dialog = builder.create()

        // Actions that must close this dialog and continue elsewhere in
        // the preview live inside the view: an AlertDialog gets only one
        // neutral button, and this dialog can need both of these.
        if (cell.hasMultiple) {
            container.addView(Button(this).apply {
                text = "Choose from ${cell.candidates.size} values…"
                setOnClickListener {
                    dialog.dismiss()
                    showCandidateChooser(itemId, tagName)
                }
            })
        }
        if (cell.manualCandidate != null) {
            container.addView(Button(this).apply {
                text = "Revert edit"
                setOnClickListener {
                    cell.clearManualEdit()
                    dialog.dismiss()
                    renderPreview()
                }
            })
        }
        dialog.show()
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
                    // A row whose cover art changes must snapshot the old
                    // APIC frame too, or undo could not restore it — that
                    // is exactly what readRawBlock's includeArtwork flag
                    // is for. Rows without a cover change keep the small
                    // artwork-free snapshot as before. (The verbatim
                    // fallback below includes every frame by definition,
                    // so cover rows are covered there as well.)
                    val changesCover = row.cells.values.any { it.changed && it.frame == "APIC" }
                    val block = try {
                        contentResolver.openInputStream(file.uri)?.use {
                            Id3Reader.readRawBlock(it, includeArtwork = changesCover)
                        }
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
                val changedCells = row.cells.values.filter { it.changed }
                // Cover art is not a text change: its cell value is a sync
                // token naming the SOURCE file, resolved to that file's
                // artwork bytes here, at apply time, and written through
                // the same temp-copy machinery as the text changes.
                val coverCell = changedCells.firstOrNull { it.frame == "APIC" }
                val changes = changedCells.filter { it.frame != "APIC" }.map { cell ->
                    TagChange(cell.frame, cell.tagName, cell.value)
                }
                if (changes.isEmpty() && coverCell == null) continue
                try {
                    val artwork = coverCell?.let { cell ->
                        val sourceId = coverTokenSourceId(cell.value)
                            ?: throw IllegalStateException("Cover change has no source file to copy from")
                        readSourceArtwork(sourceId)
                            ?: throw IllegalStateException("Could not read the cover art from the sync source file")
                    }
                    writeOneFile(file.uri, changes, artwork)
                    filesWritten++
                    for (cell in changedCells) {
                        // The log's Source column is the selected
                        // candidate's source name ("manual edit" for a
                        // hand edit). Cover values are shown as the
                        // presence marker, never the internal token.
                        val source = cell.candidates.getOrNull(cell.selected)?.sourceName ?: ""
                        logRows += ChangeLog.row(
                            logStamp, file.item.displayName, cell.tagName,
                            cell.frame,
                            displayValueOf(cell, cell.oldValue),
                            displayValueOf(cell, cell.value),
                            source,
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

    /**
     * Read the artwork bytes of one sync SOURCE file, through the same
     * temp-copy machinery as every other jaudiotagger read: the source
     * document is copied to a temp file (read-only — the source library
     * is never written) and its first cover image is extracted.
     */
    private fun readSourceArtwork(sourceItemId: String): CoverArtwork? {
        val source = syncSourceById[sourceItemId] ?: return null
        val temp = File.createTempFile("mp3tagger-cover", ".mp3", cacheDir)
        try {
            contentResolver.openInputStream(source.uri)?.use { input ->
                temp.outputStream().use { input.copyTo(it) }
            } ?: throw IllegalStateException("Could not open the sync source file")
            return JauTagIO.readArtwork(temp)
        } finally {
            temp.delete()
        }
    }

    /**
     * Rewrite one document's tags via a temp file + jaudiotagger. When
     * [artwork] is non-null the file's cover art is replaced in the same
     * temp copy, before the result is streamed back — one write-back per
     * file either way.
     */
    private fun writeOneFile(uri: Uri, changes: List<TagChange>, artwork: CoverArtwork? = null) {
        val temp = File.createTempFile("mp3tagger-write", ".mp3", cacheDir)
        try {
            contentResolver.openInputStream(uri)?.use { input ->
                temp.outputStream().use { input.copyTo(it) }
            } ?: throw IllegalStateException("Could not open file for writing")
            if (changes.isNotEmpty() || artwork == null) JauTagIO.writeTags(temp, changes)
            if (artwork != null) JauTagIO.writeArtwork(temp, artwork)
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

    /** Item id -> path relative to the picked folder, for export's FilePath column. */
    private fun scannedPaths(): Map<String, String> =
        scanned.associate { it.item.id to it.relativePath }

    private fun exportTags() {
        if (treeUri == null) {
            showMessage("Export tags", "Pick your music folder first.")
            return
        }
        // Two ways out: a fresh CSV, or merging this scan into a
        // library CSV that already exists (built up folder by folder).
        AlertDialog.Builder(this)
            .setTitle("Export tags to CSV")
            .setItems(arrayOf("New CSV", "Append to existing CSV")) { _, which ->
                when (which) {
                    0 -> lifecycleScope.launch {
                        if (scanned.isEmpty()) scanned = scanFolder()
                        pendingExportText = exportTagsCsv(scanned.map { it.item }, scannedPaths())
                        createExport.launch("mp3-tags.csv")
                    }
                    1 -> openAppendTarget.launch(
                        arrayOf("text/csv", "text/comma-separated-values", "text/plain", "*/*")
                    )
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    /**
     * Merge the current folder's scan into the library CSV at [uri]
     * and write the merged CSV back over it. Rows are keyed by the
     * FilePath column; see the engine's appendTagsCsv for the rules.
     */
    private suspend fun appendExportTo(uri: Uri) {
        if (scanned.isEmpty()) scanned = scanFolder()
        try {
            val result = runIo("Merging into ${displayName(uri)}…") {
                val existingText = contentResolver.openInputStream(uri)?.use {
                    it.readBytes().toString(Charsets.UTF_8)
                } ?: throw IllegalStateException("Could not read that CSV.")
                val merged = appendTagsCsv(existingText, scanned.map { it.item }, scannedPaths())
                contentResolver.openOutputStream(uri, "wt")?.use { out ->
                    out.write(merged.csvText.toByteArray(Charsets.UTF_8))
                } ?: throw IllegalStateException("Could not write that CSV.")
                merged.summary
            }
            val lines = mutableListOf(
                "Scanned ${result.filesScanned} file(s) into ${displayName(uri)}:",
                "Rows added: ${result.rowsAdded}",
                "Rows updated: ${result.rowsUpdated}",
                "Rows kept: ${result.rowsKept}",
            )
            if (result.columnsAdded.isNotEmpty()) {
                lines += "Columns added: ${result.columnsAdded.joinToString(", ")}"
            }
            if (result.warning != null) lines += "Warning: ${result.warning}"
            showMessage("Append to existing CSV", lines.joinToString("\n"))
            setStatus(
                "Append export: ${result.rowsAdded} added, " +
                    "${result.rowsUpdated} updated, ${result.rowsKept} kept."
            )
        } catch (e: Exception) {
            showMessage("Append to existing CSV", e.message ?: "The merge failed.")
        }
    }

    // ------------------------------------------------------------------
    // Round 2: shared scan helper for the read-only tools and sync
    // ------------------------------------------------------------------

    /**
     * Make sure the working folder has been scanned, scanning it now if
     * needed. Returns false (after telling the user) when there is no
     * folder to scan.
     */
    private suspend fun ensureScanned(): Boolean {
        if (treeUri == null) {
            showMessage("No folder", "Pick your music folder first.")
            return false
        }
        if (scanned.isEmpty()) scanned = scanFolder()
        return true
    }

    /** Hand plain text to the share sheet (reports are shared this way). */
    private fun shareText(subject: String, text: String) {
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_SUBJECT, subject)
            putExtra(Intent.EXTRA_TEXT, text)
        }
        try {
            startActivity(Intent.createChooser(intent, subject))
        } catch (e: ActivityNotFoundException) {
            showMessage(subject, "No app is available to share text with.")
        }
    }

    // ------------------------------------------------------------------
    // Round 2: tag sync from another folder
    // ------------------------------------------------------------------

    private fun syncClicked() {
        if (busy) return
        if (treeUri == null) {
            showMessage("Sync tags", "Pick your music folder first — it is the folder sync writes to (through the preview).")
            return
        }
        pickSyncTree.launch(null)
    }

    /**
     * Scan the picked SOURCE folder, pair it with the working folder's
     * scan by relative path, and let the user choose what to copy. The
     * source folder is only ever read.
     */
    private suspend fun startSyncWith(sourceTree: Uri) {
        try {
            if (!ensureScanned()) return
            val sourceName = DocumentFile.fromTreeUri(this, sourceTree)?.name ?: "source folder"
            val sourceScanned = scanTree(sourceTree, sourceName).files
            if (sourceScanned.isEmpty()) {
                showMessage("Sync tags", "No MP3 files were found in that folder.")
                return
            }
            val plan = pairLibraries(
                sourceFiles = sourceScanned.map { it.item },
                targetFiles = scanned.map { it.item },
                sourceRelativePaths = sourceScanned.associate { it.item.id to it.relativePath },
                targetRelativePaths = scanned.associate { it.item.id to it.relativePath },
            )
            if (plan.pairs.isEmpty()) {
                showMessage(
                    "Sync tags",
                    "No files paired up. Sync pairs files by their path relative to each " +
                        "folder, so the source folder must mirror this folder's layout.\n\n" +
                        "${sourceScanned.size} source file(s) and ${scanned.size} file(s) " +
                        "here were left unpaired.",
                )
                return
            }
            showSyncOptionsDialog(plan, sourceScanned)
        } catch (e: Exception) {
            showMessage("Sync tags", e.message ?: "The sync scan failed.")
        }
    }

    /** Pairing summary + which tags (and cover art) to copy, before any preview is built. */
    private fun showSyncOptionsDialog(
        plan: com.devxen.mp3csvtagger.engine.SyncPlan,
        sourceScanned: List<ScannedFile>,
    ) {
        val tags = defaultSyncTags(plan, sourceScanned.map { it.item })
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(0))
        }
        container.addView(TextView(this).apply {
            text = "Paired ${plan.pairs.size} file(s) by relative path.\n" +
                "${plan.unpairedSource.size} source file(s) have no match in this folder.\n" +
                "${plan.unpairedTarget.size} file(s) in this folder have no match in the source.\n\n" +
                "Tick the tags to copy. A tag is copied only where the source value is " +
                "non-empty and differs — sync never erases a value here with an empty one " +
                "from the source, and unpaired files are never touched."
        })
        val tagChecks = tags.map { tagName ->
            CheckBox(this).apply {
                text = tagName
                isChecked = true
            }.also { container.addView(it) }
        }
        val coverCheck = CheckBox(this).apply {
            text = COVER_TAG_NAME
            isChecked = true
        }
        container.addView(coverCheck)

        AlertDialog.Builder(this)
            .setTitle("Sync tags from another folder")
            .setView(ScrollView(this).apply { addView(container) })
            .setPositiveButton("Build preview") { _, _ ->
                val selected = tagChecks.filter { it.isChecked }.map { it.text.toString() }
                lifecycleScope.launch {
                    buildSyncPreview(plan, sourceScanned, selected, coverCheck.isChecked)
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    /**
     * Turn the chosen sync options into a [ValuesSource] layer named
     * "tag sync" and build the ordinary preview with it, so the user
     * reviews every proposed change and Apply / change log / snapshot
     * undo work exactly as for any other layer.
     */
    private suspend fun buildSyncPreview(
        plan: com.devxen.mp3csvtagger.engine.SyncPlan,
        sourceScanned: List<ScannedFile>,
        selectedTags: List<String>,
        includeCover: Boolean,
    ) {
        val values = withContext(Dispatchers.Default) {
            buildSyncValues(
                plan = plan,
                sourceFiles = sourceScanned.map { it.item },
                targetFiles = scanned.map { it.item },
                tags = selectedTags,
                includeCover = includeCover,
            )
        }
        if (values.isEmpty()) {
            showMessage(
                "Sync tags",
                "No differences to copy: for the ticked tags, every paired file here " +
                    "already matches the source (or the source value is empty).",
            )
            return
        }
        // Kept for the apply step: a cover cell's token names its source
        // file, whose artwork bytes are read only if that file is written.
        syncSourceById = sourceScanned.associateBy { it.item.id }
        // A re-run replaces the previous sync layer instead of stacking a
        // second one whose values were computed from an older scan.
        layers.removeAll { it is ValuesSource && it.name == SYNC_SOURCE_NAME }
        layers += ValuesSource(SYNC_SOURCE_NAME, values)
        preview = null
        saveState()
        renderAll()
        buildPreviewClicked()
    }

    // ------------------------------------------------------------------
    // Round 2: consistency check (read-only)
    // ------------------------------------------------------------------

    private fun consistencyClicked() {
        if (busy) return
        lifecycleScope.launch {
            if (!ensureScanned()) return@launch
            val input = EditText(this@MainActivity).apply {
                setText("{Artist}/{Album}/{Track} - {Title}")
                setSelection(text.length)
            }
            val container = LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(16), dp(8), dp(16), dp(0))
                addView(TextView(this@MainActivity).apply {
                    text = "Compare each file's tags with the values its folder and file " +
                        "names claim, using this filename pattern. This only reports " +
                        "disagreements — it never changes a tag."
                })
                addView(input)
            }
            AlertDialog.Builder(this@MainActivity)
                .setTitle("Consistency check")
                .setView(container)
                .setPositiveButton("Run check") { _, _ ->
                    val pattern = input.text.toString().trim()
                    if (pattern.isEmpty()) return@setPositiveButton
                    lifecycleScope.launch {
                        val result = withContext(Dispatchers.Default) {
                            checkConsistency(
                                files = scanned.map { it.item },
                                relativePaths = scannedPaths(),
                                pattern = pattern,
                            )
                        }
                        showConsistencyResults(pattern, result)
                    }
                }
                .setNegativeButton("Cancel", null)
                .show()
        }
    }

    private fun showConsistencyResults(
        pattern: String,
        result: com.devxen.mp3csvtagger.engine.ConsistencyResult,
    ) {
        val byId = scanned.associateBy { it.item.id }
        val report = buildString {
            append("Consistency check\nPattern: $pattern\n\n")
            append("Checked ${result.checked} file(s); ")
            append("${result.unmatched.size} file(s) did not match the pattern and were not checked.\n")
            append("${result.mismatches.size} mismatch(es).\n")
            if (result.mismatches.isEmpty()) {
                append("\nNo mismatches — the tags agree with the file layout everywhere the pattern matched.")
            } else {
                append("\n")
                for (mismatch in result.mismatches) {
                    val path = byId[mismatch.itemId]?.relativePath ?: mismatch.itemId
                    val tagValue = mismatch.tagValue.ifEmpty { "(empty)" }
                    append("• $path — ${mismatch.tag}: path says \"${mismatch.pathValue}\", tag says \"$tagValue\"\n")
                }
            }
        }
        AlertDialog.Builder(this)
            .setTitle("Consistency check")
            .setMessage(report.trimEnd())
            .setPositiveButton("Share report") { _, _ -> shareText("Consistency report", report) }
            .setNegativeButton("Close", null)
            .show()
    }

    // ------------------------------------------------------------------
    // Round 2: library report (read-only)
    // ------------------------------------------------------------------

    private fun libraryReportClicked() {
        if (busy) return
        lifecycleScope.launch {
            if (!ensureScanned()) return@launch
            val report = withContext(Dispatchers.Default) {
                val items = scanned.map { it.item }
                buildString {
                    append(renderCompletenessText(albumCompleteness(items)))
                    append("\nDuplicates (same title and performer)\n")
                    append("=====================================\n")
                    val duplicates = duplicateGroups(items)
                    if (duplicates.isEmpty()) {
                        append("None found.\n")
                    } else {
                        for (group in duplicates) {
                            append("• \"${group.title}\" — ${group.artist} (${group.itemIds.size} file(s))\n")
                        }
                    }
                    for (tagName in listOf("Lead Performer", "Album", "Genre")) {
                        val variants = variantGroups(items, tagName)
                        if (variants.isEmpty()) continue
                        append("\nSpelling variants — $tagName\n")
                        append("=====================================\n")
                        for (group in variants) {
                            val spellings = group.spellings.keys.joinToString(" / ") { "\"$it\"" }
                            val count = group.spellings.values.sumOf { it.size }
                            append("• $spellings ($count file(s))\n")
                        }
                    }
                }
            }
            AlertDialog.Builder(this@MainActivity)
                .setTitle("Library report")
                .setMessage(report.trimEnd())
                .setPositiveButton("Share report") { _, _ -> shareText("Library report", report) }
                .setNegativeButton("Close", null)
                .show()
        }
    }

    // ------------------------------------------------------------------
    // Round 2: named jobs + launcher shortcuts
    // ------------------------------------------------------------------

    /** Where saved jobs live: one JSON file per job, app-private. */
    private fun jobsDir(): File = File(filesDir, "jobs").apply { mkdirs() }

    private fun jobFileName(name: String): String =
        name.replace(Regex("[^A-Za-z0-9._-]"), "_") + ".json"

    /** Every saved job on disk, paired with its file, sorted by name. */
    private fun loadSavedJobFiles(): List<Pair<File, Job>> {
        val dir = jobsDir()
        val files = dir.listFiles { f -> f.isFile && f.name.endsWith(".json") } ?: return emptyList()
        return files.mapNotNull { file ->
            runCatching { file to Job.fromJsonString(file.readText(Charsets.UTF_8)) }.getOrNull()
        }.sortedBy { it.second.name.lowercase() }
    }

    /** Every saved job, sorted by name. */
    private fun loadSavedJobs(): List<Job> = loadSavedJobFiles().map { it.second }

    private fun saveJobClicked() {
        val input = EditText(this).apply { hint = "Job name" }
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(0))
            addView(TextView(this@MainActivity).apply {
                text = "Save the current folder and layer setup under a name, so the " +
                    "whole run can be rebuilt later in one tap (Jobs… or a launcher shortcut)."
            })
            addView(input)
        }
        AlertDialog.Builder(this)
            .setTitle("Save current job")
            .setView(container)
            .setPositiveButton("Save job") { _, _ ->
                val name = input.text.toString().trim()
                if (name.isEmpty()) return@setPositiveButton
                val jobLayers = mutableListOf<JobLayer>()
                for (layer in layers) {
                    when (layer) {
                        is CsvSource -> jobLayers += JobCsvLayer(
                            csvUri = layer.csv.id,
                            included = layer.csv.included,
                            roles = layer.csv.tags.associate { it.name to it.role },
                        )
                        is FilenamePatternSource -> jobLayers += JobPatternLayer(
                            pattern = layer.pattern,
                            included = layer.included,
                        )
                        // Computed values (tag sync) belong to one scan of
                        // another folder; a job cannot rebuild them, so
                        // they are not part of a saved setup.
                        is ValuesSource -> Unit
                    }
                }
                // The alternative-name map is saved with the job by the
                // engine model; this app resolves headings with the
                // default map everywhere, so that is what the job records.
                val job = Job(
                    name = name,
                    treeUri = treeUri?.toString() ?: "",
                    layers = jobLayers,
                )
                File(jobsDir(), jobFileName(name)).writeText(job.toJsonString(), Charsets.UTF_8)
                publishJobShortcuts(loadSavedJobs())
                showMessage("Save current job", "Saved job \"$name\". Find it under Jobs…")
                setStatus("Saved job \"$name\".")
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showJobsDialog() {
        val saved = loadSavedJobFiles()
        if (saved.isEmpty()) {
            showMessage("Jobs", "No saved jobs yet. Set up a folder and layers, then tap \"Save current job…\".")
            return
        }
        val names = saved.map { it.second.name }.toTypedArray()
        AlertDialog.Builder(this)
            .setTitle("Jobs")
            .setItems(names) { _, which ->
                val (file, job) = saved[which]
                AlertDialog.Builder(this)
                    .setTitle(job.name)
                    .setMessage(
                        "Folder: ${job.treeUri.ifEmpty { "(none saved)" }}\n" +
                            "Layers: ${job.layers.size}",
                    )
                    .setPositiveButton("Run") { _, _ ->
                        lifecycleScope.launch { runJob(job) }
                    }
                    .setNegativeButton("Delete") { _, _ ->
                        file.delete()
                        publishJobShortcuts(loadSavedJobs())
                        setStatus("Deleted job \"${job.name}\".")
                    }
                    .setNeutralButton("Cancel", null)
                    .show()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    /**
     * Rebuild a saved job's state — folder, layers with their roles —
     * then scan and build the ordinary preview, exactly as if the user
     * had set it all up by hand.
     */
    private suspend fun runJob(job: Job) {
        try {
            if (job.treeUri.isNotEmpty()) {
                treeUri = Uri.parse(job.treeUri)
                treeName = DocumentFile.fromTreeUri(this, treeUri!!)?.name ?: "music folder"
            }
            layers.clear()
            for (layer in job.layers) {
                when (layer) {
                    is JobCsvLayer -> loadCsvSource(Uri.parse(layer.csvUri))?.let { source ->
                        source.csv.included = layer.included
                        // The job's roles win over any remembered roles.
                        for (tag in source.csv.tags) {
                            layer.roles[tag.name]?.let { tag.role = it }
                        }
                        layers += source
                    }
                    is JobPatternLayer -> layers += FilenamePatternSource(
                        pattern = layer.pattern,
                        included = layer.included,
                    )
                }
            }
            scanned = emptyList()
            preview = null
            saveState()
            renderAll()
            setStatus("Running job \"${job.name}\"…")
            buildPreviewClicked()
        } catch (e: Exception) {
            showMessage("Jobs", e.message ?: "The job could not be run.")
        }
    }

    /**
     * Publish up to four dynamic launcher shortcuts, one per saved job
     * (first four by name). A shortcut relaunches the app with the
     * [ACTION_RUN_JOB] action; onCreate/onNewIntent route it to [runJob].
     */
    private fun publishJobShortcuts(jobs: List<Job>) {
        try {
            val shortcuts = jobs.take(4).map { job ->
                val intent = Intent(this, MainActivity::class.java).apply {
                    action = ACTION_RUN_JOB
                    putExtra(EXTRA_JOB_NAME, job.name)
                }
                val label = "Run ${job.name}".let {
                    if (it.length > 25) it.take(24) + "…" else it
                }
                ShortcutInfoCompat.Builder(this, "job:${job.name}")
                    .setShortLabel(label)
                    .setLongLabel("Run job ${job.name}")
                    .setIcon(IconCompat.createWithBitmap(jobShortcutIcon()))
                    .setIntent(intent)
                    .build()
            }
            ShortcutManagerCompat.setDynamicShortcuts(this, shortcuts)
        } catch (e: Exception) {
            // Shortcut publishing is best-effort (launchers may refuse);
            // the Jobs… list inside the app always works.
        }
    }

    /** A simple drawn icon for job shortcuts: a music note on a dark plate. */
    private fun jobShortcutIcon(): Bitmap {
        val size = 96
        val bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        canvas.drawColor(Color.rgb(24, 24, 24))
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
            textSize = 56f
            textAlign = Paint.Align.CENTER
        }
        canvas.drawText("♪", size / 2f, size / 2f + 20f, paint)
        return bitmap
    }

    // ------------------------------------------------------------------
    // Round 2: CSV files arriving through Open-with / the share sheet
    // ------------------------------------------------------------------

    /**
     * Copy an incoming CSV (a VIEW data URI or a SEND stream) into
     * app-private storage and add the COPY as a layer. The copy matters:
     * the grant behind a shared/opened document is temporary, so a layer
     * pointing at the original could stop working — the private copy
     * keeps the layer (and its saved-state entry) working across
     * restarts with no grant at all.
     */
    private suspend fun importSharedCsv(incoming: Uri) {
        try {
            val copy = runIo("Importing CSV…") {
                val dir = File(filesDir, "imported_csv").apply { mkdirs() }
                val rawName = displayName(incoming)
                val sanitised = rawName.replace(Regex("[^A-Za-z0-9._-]"), "_")
                val stem = sanitised.replace(Regex("(?i)\\.csv$"), "").ifEmpty { "shared" }
                val target = File(dir, "$stem-${System.currentTimeMillis()}.csv")
                val input = contentResolver.openInputStream(incoming)
                    ?: throw IllegalStateException("Could not open the shared CSV")
                input.use { stream -> target.outputStream().use { stream.copyTo(it) } }
                target
            }
            val source = loadCsvSource(Uri.fromFile(copy)) ?: return
            layers += source
            preview = null
            saveState()
            renderAll()
            setStatus("Imported CSV added as a layer: ${copy.name}")
        } catch (e: Exception) {
            showMessage("Import CSV", e.message ?: "The shared CSV could not be imported.")
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
