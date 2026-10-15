// Top-level build file.
//
// Plugins come in via the buildscript classpath (not the plugins{} version
// DSL) because the Gradle Plugin Portal redirects some plugin markers to
// Maven Central where they 404 in this build environment; resolving AGP and
// the Kotlin plugin as ordinary classpath dependencies is the reliable path.
buildscript {
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        classpath("com.android.tools.build:gradle:8.5.2")
        classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:2.0.20")
    }
}
