import java.io.File
import java.util.Properties

// Release signing: the per-app keystore and its password file live OUTSIDE
// the repo (never in git) at ~/workspace/homebrew/keys/.
//   mp3tagger-release.keystore + mp3tagger-password.txt
// If they are absent (e.g. a fresh clone on another machine) the release
// build falls back to the debug key so the project still compiles; such an
// APK is NOT the shipped build — the release process verifies the signer.
val keystoreFile = File("/home/hatch/workspace/homebrew/keys/mp3tagger-release.keystore")
val passwordFile = File("/home/hatch/workspace/homebrew/keys/mp3tagger-password.txt")
// Named keystorePassword (not storePassword) so it is not shadowed by the
// SigningConfig property of the same name inside the signingConfigs block.
val keystorePassword = if (passwordFile.exists()) passwordFile.readText().trim() else ""

plugins {
    // Versions are supplied by the root buildscript classpath.
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.devxen.mp3csvtagger"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.devxen.mp3csvtagger"
        minSdk = 26
        targetSdk = 34
        versionCode = 3
        versionName = "1.2.0"
    }

    signingConfigs {
        if (keystoreFile.exists()) {
            create("release") {
                storeFile = keystoreFile
                storePassword = keystorePassword
                keyAlias = "mp3tagger"
                keyPassword = keystorePassword
            }
        }
    }

    lint {
        // Release lint needs artifacts that are not fetchable in every
        // build environment; correctness is gated by unit tests + the
        // packaged-APK checks (badging/signer/dex inventory) instead.
        checkReleaseBuilds = false
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.findByName("release")
                ?: signingConfigs.getByName("debug")
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    // AndroidX basics: Activity Result contracts (SAF pickers), DocumentFile
    // (tree walking) and coroutines for doing tag IO off the main thread.
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-ktx:1.9.2")
    implementation("androidx.documentfile:documentfile:1.0.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.5")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")

    // ID3 read/write. Pure Java, the standard library for this job; it
    // preserves frames we do not touch (artwork included) when writing.
    implementation("net.jthink:jaudiotagger:3.0.1")

    testImplementation("junit:junit:4.13.2")
    // The engine's job (de)serialisation uses org.json, which Android
    // provides at runtime — but in local JVM unit tests the android.jar
    // copy is a stub whose methods throw. The real org.json library as a
    // TEST-ONLY dependency shadows the stub so the job format is tested
    // against the genuine implementation; the shipped APK still uses
    // the framework's built-in copy and gains no dependency.
    testImplementation("org.json:json:20240303")
}
