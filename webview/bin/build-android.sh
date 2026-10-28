#!/usr/bin/env bash
# Android build Docker-ով (տեղական SDK պետք չէ). Արդյունքը՝ webview/out/{debug,release}/*.apk
# Օրինակ՝ bin/build-android.sh                  (debug + release-unsigned)
#         bin/build-android.sh assembleDebug    (միայն debug)
set -euo pipefail
cd "$(dirname "$0")/.."
TASKS="${*:-assembleDebug assembleRelease}"
DOCKER_BUILDKIT=1 docker build -f Dockerfile.android --build-arg TASKS="$TASKS" -o out .
find out -name '*.apk' -exec ls -la {} \;
