#!/usr/bin/env bash
# Դեսկտոպ build. macOS-ի .dmg-ն սարքվում է միայն Mac-ի վրա։
# Օրինակ՝ bin/build-desktop.sh win-docker  (Windows՝ Docker-ով, wine-ը տեղադրելու կարիք չկա)
#         bin/build-desktop.sh win         (Windows՝ տեղական wine-ով)
#         bin/build-desktop.sh mac         (macOS, պետք է Mac)
#         bin/build-desktop.sh linux       (AppImage + deb)
#         bin/build-desktop.sh             (ընթացիկ համակարգի համար՝ չփաթեթավորված պանակ)
set -euo pipefail
cd "$(dirname "$0")/../desktop"

# NSIS-ի ինստալյատորը (uninstaller-ի քայլը) wine է պահանջում. Linux-ի վրա այն սովորաբար չկա,
# ուստի Docker-ի պատրաստի պատկերը ամենակարճ ճանապարհն է։ Կոնտեյները աշխատում է ՄԵՐ uid-ով,
# որ out/-ը root-ի չդառնա, իսկ HOME-ը (wine-ի prefix, քեշեր) գնում է webview/.dockerhome-ի մեջ։
win_docker() {
    cd ..
    mkdir -p .dockerhome
    docker run --rm --user "$(id -u):$(id -g)" \
        -e HOME=/project/.dockerhome \
        -e ELECTRON_CACHE=/project/.dockerhome/.cache/electron \
        -e ELECTRON_BUILDER_CACHE=/project/.dockerhome/.cache/electron-builder \
        -v "$PWD:/project" -w /project/desktop \
        electronuserland/builder:wine \
        npx electron-builder --config electron-builder.config.cjs --win
}

[ -d node_modules ] || npm install
case "${1:-dir}" in
    win-docker) win_docker ;;
    win)
        command -v wine >/dev/null || { echo "wine չկա. գործարկիր՝ $0 win-docker" >&2; exit 1; }
        npm run dist:win ;;
    mac) npm run dist:mac ;;
    linux) npm run dist:linux ;;
    dir) npm run pack ;;
    *) echo "Օգտագործում՝ $0 [win-docker|win|mac|linux|dir]" >&2; exit 1 ;;
esac
ls -la ../out/desktop
