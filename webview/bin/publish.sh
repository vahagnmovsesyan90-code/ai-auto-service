#!/usr/bin/env bash
# Պատրաստի փաթեթները դնում է կայքի ներբեռնման պանակում (/download էջը դրանք ինքն է գտնում)։
#
#   bin/publish.sh                 # webview/out-ի ամեն ինչը՝ app.json-ի տարբերակներով
#   bin/publish.sh 1.2.0           # տարբերակը ձեռքով (այլապես՝ app.json-ից)
#
# Անունը խիստ է. aiauto-<տարբերակ>-<հարթակ>[-<ճարտարապետություն>].<ext>
# Հին տարբերակները չեն ջնջվում. պանակից ձեռքով հանելը բավական է, որ էջից անհետանան։
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(cd .. && pwd)"
DEST="$ROOT/downloads"
VER="${1:-}"

json() { python3 -c "import json,sys;print(json.load(open('app.json'))$1)"; }

mkdir -p "$DEST"

# Մեկ ֆայլ՝ նոր անունով. արդեն նույնը լինելիս ձեռք չի տալիս։
# Կիսատ build-ը թողնում է խաբուսիկ փոքր ֆայլեր (օր. wine-ի սխալից հետո՝ 300 ԿԲ-անոց
# NSIS stub առանց հավելվածի). այդպիսին կայք չի գնում
put() {
    local src="$1" name="$2" min="${3:-0}"
    if [ "$min" -gt 0 ] && [ "$(stat -c%s "$src")" -lt "$min" ]; then
        echo "ԲԱՑ ԹՈՂՆՎԱԾ. $src-ը չափազանց փոքր է ($(du -h "$src" | cut -f1)) — build-ը կիսատ է" >&2
        return
    fi
    if [ -f "$DEST/$name" ] && cmp -s "$src" "$DEST/$name"; then
        echo "= $name"
        return
    fi
    cp -f "$src" "$DEST/$name.tmp"
    mv -f "$DEST/$name.tmp" "$DEST/$name"   # կիսատ ֆայլ չերևա էջին
    echo "+ $name  ($(du -h "$DEST/$name" | cut -f1))"
}

# ── Android ── ստորագրված release-ը գերադասելի է, չլինելու դեպքում՝ debug-ը
AVER="${VER:-$(json "['android']['versionName']")}"
# Ստորագրված release-ը լավագույնն է. չլինելու դեպքում debug-ը (այն գոնե տեղադրվում է),
# ու միայն վերջում՝ unsigned release-ը՝ բարձրաձայն զգուշացումով
APK="$(ls -t out/release/*.apk 2>/dev/null | grep -v unsigned | head -1 || true)"
[ -n "$APK" ] || APK="$(ls -t out/debug/*.apk 2>/dev/null | head -1 || true)"
[ -n "$APK" ] || APK="$(ls -t out/release/*.apk 2>/dev/null | head -1 || true)"
if [ -n "$APK" ]; then
    case "$APK" in
        *unsigned*) echo "ՈՒՇԱԴՐՈՒԹՅՈՒՆ. $APK-ը ստորագրված չէ՝ Android-ը այն չի տեղադրի (պետք է signingConfig)" >&2 ;;
        *debug*) echo "ՆՇՈՒՄ. հրապարակվում է debug-փաթեթը. կայքի համար պետք է ստորագրված release" >&2 ;;
    esac
    put "$APK" "aiauto-$AVER-android.apk"
fi

# ── Desktop (electron-builder) ── ճարտարապետությունը անունից՝ arm64 / x64
DVER="${VER:-$(json "['desktop']['version']")}"
for f in out/desktop/*.exe out/desktop/*.msi out/desktop/*.dmg out/desktop/*.AppImage out/desktop/*.deb; do
    [ -f "$f" ] || continue
    ext="${f##*.}"
    case "$ext" in
        exe|msi) plat=windows ;;
        dmg) plat=macos ;;
        AppImage|deb) plat=linux ;;
    esac
    arch=""
    case "$f" in
        *arm64*) arch="-arm64" ;;
        *x86_64*|*x64*|*amd64*) arch="-x64" ;;
    esac
    # electron-builder-ը սարքում է նաև «երկուսը մեկում» ֆայլ (x64 + arm64 մեկ ինստալյատորում,
    # կրկնակի ծանր). եթե առանձին ճարտարապետությունները կան, կայքին այն պետք չէ
    if [ -z "$arch" ]; then
        both=0
        for g in out/desktop/*."$ext"; do
            case "$g" in *arm64*|*x86_64*|*x64*|*amd64*) both=1 ;; esac
        done
        if [ "$both" = 1 ]; then
            echo "ԲԱՑ ԹՈՂՆՎԱԾ. $f՝ առանց ճարտարապետության (կան առանձին x64/arm64)" >&2
            continue
        fi
    fi
    put "$f" "aiauto-$DVER-$plat$arch.$ext" $((20 * 1024 * 1024))
done

# Կոնտեյներում ֆայլերը կարդում է հավելվածը (docker-compose-ի ./downloads volume-ը)
chmod 0644 "$DEST"/* 2>/dev/null || true
echo
echo "Պանակը՝ $DEST"
ls -la "$DEST"
echo "Ստուգիր՝ curl -s localhost:8000/api/downloads | head -40"
