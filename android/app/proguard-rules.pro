# Release builds are not minified in v1 (isMinifyEnabled = false), so this
# file is intentionally empty of app rules. jaudiotagger is consumed as a
# plain library jar; if minification is enabled later, keep its public API:
# -keep class org.jaudiotagger.** { *; }
