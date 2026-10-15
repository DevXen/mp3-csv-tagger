#!/bin/bash
# Build the MP3 CSV Tagger Android app (signed release APK by default).
#
# Environment notes for this sandbox (same recipe as the MusicXen build):
#  - JAVA_HOME points at the local JDK 17.
#  - GRADLE_USER_HOME reuses the shared Gradle home whose truststore holds
#    the sandbox egress CA; without it dependency downloads fail PKIX
#    validation. If downloads ever fail with "signature check failed", the
#    CA has rotated: re-import
#    /usr/local/share/ca-certificates/hatch-egress-ca.crt into
#    $GRADLE_USER_HOME/egress-cacerts and kill any Gradle daemons.
#  - JAVA_TOOL_OPTIONS forces IPv4, which this sandbox's networking needs.
#
# Usage: ./build.sh [gradle task, default: assembleRelease]
set -e
cd "$(dirname "$0")"
export JAVA_HOME=/home/hatch/workspace/homebrew/jdk/jdk-17.0.20.1+1
export GRADLE_USER_HOME=/home/hatch/workspace/musicxen/gradle-home
export JAVA_TOOL_OPTIONS="-Djava.net.preferIPv4Stack=true"
export GRADLE_OPTS="-Djavax.net.ssl.trustStore=/home/hatch/workspace/musicxen/gradle-home/egress-cacerts -Djavax.net.ssl.trustStorePassword=changeit"
if [ ! -f local.properties ]; then
  echo "sdk.dir=/home/hatch/workspace/android-sdk" > local.properties
fi
exec /home/hatch/workspace/musicxen/gradle-8.9/bin/gradle "${@:-assembleRelease}" --max-workers=1
