package com.devxen.mp3csvtagger.engine

import org.json.JSONArray
import org.json.JSONObject

/**
 * Named, reusable jobs: a saved run that can be re-run in one step.
 *
 * A *job* is everything one full tagging run needs, saved under a name:
 *
 * * the picked music folder (its SAF tree URI, as a string),
 * * the layer stack in run order — CSV layers (their document URI, their
 *   per-column roles and whether the layer is included) and
 *   filename-pattern layers — mirroring the app state the main screen
 *   already persists for itself,
 * * the alternative tag-name map.
 *
 * Running a job (a UI job: storage, pickers and shortcut publishing all
 * live there) rebuilds that state, scans, and builds the ordinary
 * preview — so a job run is indistinguishable from doing the steps by
 * hand, including its change log and snapshot undo on apply.
 *
 * This file is deliberately *only* the model plus its JSON
 * (de)serialisation: where jobs are stored (app-private files, one JSON
 * file per job) is a storage concern for the UI side, exactly as paths
 * and URIs are elsewhere in the engine. org.json is used because the
 * app already speaks it (the main screen's saved state is org.json);
 * it is a plain Java library, so the engine stays free of Android
 * framework types and JVM tests exercise the real format.
 */

/** One layer in a saved job's layer stack. */
sealed interface JobLayer {
    /** False when the user had switched this layer off. */
    val included: Boolean
}

/**
 * A CSV layer in a job: the CSV document's URI string (the same stable
 * layer id the engine's [CsvLayer] uses on Android), whether it is
 * included, and the role of each column by heading. Roles are stored
 * by their [Role.value] integers — those values are part of the shared
 * file format, so a job file stays meaningful across versions.
 */
data class JobCsvLayer(
    val csvUri: String,
    override val included: Boolean = true,
    val roles: Map<String, Role> = emptyMap(),
) : JobLayer

/** A filename-pattern layer in a job (see [FilenamePatternSource]). */
data class JobPatternLayer(
    val pattern: String,
    override val included: Boolean = true,
) : JobLayer

/**
 * One named, reusable run (see the file doc).
 *
 * [alternativeNames] defaults to the standard map; it is saved with
 * the job so a run restored later resolves headings exactly as the run
 * that was saved did, even if the defaults ever change.
 */
data class Job(
    val name: String,
    /** SAF tree URI of the picked music folder, as a string ("" if none). */
    val treeUri: String,
    /** The layer stack, in run order. */
    val layers: List<JobLayer> = emptyList(),
    val alternativeNames: Map<String, String> = TagNames.defaultAlternativeNames,
) {
    /** This job as a JSON object (the on-disk job format). */
    fun toJson(): JSONObject {
        val layersJson = JSONArray()
        for (layer in layers) {
            layersJson.put(
                when (layer) {
                    is JobCsvLayer -> JSONObject().apply {
                        put("type", "csv")
                        put("id", layer.csvUri)
                        put("included", layer.included)
                        val roles = JSONObject()
                        for ((tagName, role) in layer.roles) roles.put(tagName, role.value)
                        put("roles", roles)
                    }
                    is JobPatternLayer -> JSONObject().apply {
                        put("type", "pattern")
                        put("pattern", layer.pattern)
                        put("included", layer.included)
                    }
                }
            )
        }
        val namesJson = JSONObject()
        for ((frame, friendly) in alternativeNames) namesJson.put(frame, friendly)
        return JSONObject().apply {
            put("name", name)
            put("treeUri", treeUri)
            put("layers", layersJson)
            put("alternativeNames", namesJson)
        }
    }

    /** This job serialised as JSON text (what a job file contains). */
    fun toJsonString(): String = toJson().toString()

    companion object {
        /**
         * Build a [Job] from a JSON object such as [toJson] produces.
         *
         * Tolerant in the same places the desktop loader is: a missing
         * layer list means no layers, a missing or empty
         * alternative-name map falls back to the defaults, a missing
         * "included" means included, and a layer of an unknown type is
         * skipped rather than failing the whole job — one newer layer
         * kind must not make an older build lose the entire job.
         * A missing job *name*, though, is a malformed job and throws,
         * because a nameless job can neither be listed nor run.
         */
        fun fromJson(json: JSONObject): Job {
            val layers = mutableListOf<JobLayer>()
            val layersJson = json.optJSONArray("layers")
            if (layersJson != null) {
                for (i in 0 until layersJson.length()) {
                    val entry = layersJson.optJSONObject(i) ?: continue
                    val included = entry.optBoolean("included", true)
                    when (entry.optString("type")) {
                        "csv" -> {
                            val roles = LinkedHashMap<String, Role>()
                            val rolesJson = entry.optJSONObject("roles")
                            if (rolesJson != null) {
                                val keys = rolesJson.keys()
                                while (keys.hasNext()) {
                                    val key = keys.next()
                                    roles[key] = Role.fromValue(rolesJson.optInt(key, Role.Skip.value))
                                }
                            }
                            layers += JobCsvLayer(entry.optString("id"), included, roles)
                        }
                        "pattern" -> layers += JobPatternLayer(entry.optString("pattern"), included)
                        // Unknown layer type: skipped (see doc above).
                    }
                }
            }

            val alternativeNames = LinkedHashMap<String, String>()
            val namesJson = json.optJSONObject("alternativeNames")
            if (namesJson != null) {
                val keys = namesJson.keys()
                while (keys.hasNext()) {
                    val key = keys.next()
                    alternativeNames[key] = namesJson.optString(key)
                }
            }

            return Job(
                name = json.getString("name"),
                treeUri = json.optString("treeUri"),
                layers = layers,
                alternativeNames = if (alternativeNames.isEmpty()) {
                    TagNames.defaultAlternativeNames
                } else {
                    alternativeNames
                },
            )
        }

        /** Build a [Job] from JSON text such as [toJsonString] produces. */
        fun fromJsonString(text: String): Job = fromJson(JSONObject(text))
    }
}
