# MP3 CSV Tagger for Android

Native Kotlin companion to the desktop program: same CSV format, same
Match/Write/Skip roles, same rules. See [../docs/ANDROID.md](../docs/ANDROID.md)
for the feature list and [../docs/ANDROID_HELP.md](../docs/ANDROID_HELP.md)
for the full in-app Help text.

## Layout

* `app/src/main/java/com/devxen/mp3csvtagger/engine/` — the tagging
  engine (roles, CSV parsing, matching, layered preview, export).
  Plain Kotlin, no Android imports: it is unit-tested on the JVM
  against the same scenarios as the desktop suite.
* `.../tagio/` — ID3 stream reading, jaudiotagger writing, and the
  tag-snapshot undo format.
* `.../MainActivity.kt` — SAF pickers, scanning, preview UI, apply and
  undo flows. `HelpActivity.kt` renders `assets/help.md`.

## Build

```bash
./build.sh                    # signed release APK
./build.sh testDebugUnitTest  # JVM tests
```

`build.sh` sets up the JDK/Gradle environment this project's builds
use (see the header comment). Release signing reads the per-app
keystore from outside the repo; without it the build falls back to the
debug key and says so in `app/build.gradle.kts`.
