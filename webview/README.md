# webview — AI Auto Service-ի հավելվածները

Բնիկ (native) պատյաններ Android-ի, iOS-ի, Windows-ի, macOS-ի և Linux-ի համար, որոնք կայքը (`https://aiauto.am`) բացում են
WebView-ում։ Կայքը մնում է կայք. հավելվածը միայն «պատուհան» է։ Կառուցվածքը նույնն է, ինչ TutorVoice-ի `webview/`-ը։

| Թղթապանակ | Ինչ է |
|---|---|
| `app.json` | Ընդհանուր կոնֆիգ՝ հասցե (`url`), dev հասցե (`devUrl`՝ emulator-ից `10.0.2.2:8000` = host-ի `localhost:8000`), թույլատրված հոսթեր, UA վերջածանց (`AiAutoApp/1.0`), id-ներ ու տարբերակներ։ Կարդում են բոլոր պլատֆորմները |
| `shared/error.html` | Offline էջ, «Փորձել նորից» = `app://retry` |
| `android/` | Kotlin, minSdk 26 (Android 8+), `am.aiauto.app`։ Release-ը ստորագրվում է `android/keystore.properties` + `aiauto-release.jks`-ով (git-ում ՉԵՆ, պահեք անվտանգ տեղում. կորցնելու դեպքում թարմացում տեղադրել չի լինի) |
| `ios/` | Swift, iOS 15+, WKWebView, `am.aiauto.app`։ Xcode նախագիծը՝ `cd ios && xcodegen generate` (Mac) |
| `desktop/` | Electron (Windows 10+, macOS 11+, Linux), `am.aiauto.desktop` |
| `bin/build-android.sh` | APK Docker-ով (`cimg/android`), առանց տեղական SDK-ի → `out/debug/`, `out/release/` |
| `bin/build-desktop.sh` | `linux` (AppImage + deb), `win-docker` (NSIS՝ Docker-ի wine պատկերով), `mac` (միայն Mac-ի վրա), `dir` |
| `bin/publish.sh` | Պատրաստի փաթեթները տանում է `../downloads/`՝ `aiauto-<տարբերակ>-<հարթակ>[-<ճարտ.>].<ext>` անունով. կայքի `/download` էջը և ադմինի «Հավելվածներ» բաժինը դրանք ինքնուրույն գտնում են (`GET /api/downloads`) |

## Ինչ է անում պատյանը
- Կայքի հղումները (`hosts`) բացվում են հավելվածում, մնացածը (`tel:`, քարտեզի հավելվածներ, այլ կայք)՝ համակարգում։
- Ֆայլի ընտրիչ, ներբեռնումներ (Android՝ Downloads, iOS՝ share sheet, դեսկտոպ՝ «Պահել»), cookie-ներ/session (ադմինի մուտքը մնում է)։
- Offline՝ `shared/error.html`, Android-ում ինքն է վերականգնվում, երբ կայքը նորից հասանելի է։
- Android back, iOS swipe-back, դեսկտոպում մենյու (հետ/առաջ, zoom, լիաէկրան), պատուհանի չափի հիշում, մեկ օրինակ, tray։
- User-Agent-ի վերջածանցը `AiAutoApp/1.0` է. `/download` էջը դրանով հասկանում է, որ արդեն հավելվածից են մտել։
- Android App Links՝ կայքի `/.well-known/assetlinks.json`-ը (նախագծի արմատի `assetlinks.json`, release բանալու SHA-256-ով) արդեն տրվում է API-ից։
- Push (FCM/APNs) կոդը պահված է, բայց սերվերը դեռ չի ուղարկում. առանց `google-services.json`-ի Android-ը հավաքվում է առանց push-ի։

## Կառուցում և հրապարակում
```bash
cd webview
bin/build-android.sh              # debug + ստորագրված release → out/
bin/build-desktop.sh linux        # AppImage + deb (x64, arm64)
bin/build-desktop.sh win-docker   # Windows ինստալյատոր (x64, arm64), Docker-ով
bin/build-desktop.sh mac          # .dmg՝ միայն macOS-ի վրա (ստորագրում/notarization՝ Apple Developer հաշվով)
bin/publish.sh                    # → ../downloads/  (տարբերակը app.json-ից, կամ bin/publish.sh 1.1.0)
```
Տարբերակը բարձրացնելիս փոխեք `app.json`-ում `android.versionCode`/`versionName` և `desktop.version`։
Windows-ի ինստալյատորը ստորագրված չէ (SmartScreen-ի զգուշացում). code signing-ի համար՝ `CSC_LINK`, `CSC_KEY_PASSWORD`։
iOS-ը տեղադրվում է միայն App Store/TestFlight-ով. հրապարակելուց հետո հղումը՝ `.env`-ում `APP_STORE_URL` (Google Play-ի համար՝ `PLAY_STORE_URL`)։

## Dev
- Android emulator՝ debug build-ը բացում է `http://10.0.2.2:8000` (host-ի `uvicorn api:app --port 8000`)։
- Դեսկտոպ՝ `cd desktop && npm install && npm start` (dev հասցե) կամ `npm run start:prod`։
