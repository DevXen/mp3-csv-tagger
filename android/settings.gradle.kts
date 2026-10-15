// MP3 CSV Tagger — Android companion app settings.
// A single-module app on purpose: the whole product is one tagging tool,
// and one module keeps the build (and the APK) small and auditable.
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "Mp3CsvTagger"
include(":app")
