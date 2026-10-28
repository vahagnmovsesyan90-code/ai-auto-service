/**
 * electron-builder-ի կոնֆիգը. անունը, id-ն ու վերսիան կարդացվում են ../app.json-ից,
 * որ դեսկտոպը, Android-ը և iOS-ը մեկ տեղից կառավարվեն։ Արդյունքը՝ webview/out/desktop/։
 */
const fs = require('node:fs');
const path = require('node:path');

const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'app.json'), 'utf8'));
const desktop = cfg.desktop || {};
const appId = desktop.appId || 'am.aiauto.desktop';
const version = desktop.version || '1.0.0';
const summary = desktop.summary || {};
const description = desktop.description || {};

/*
 * AppStream-ի քարտը (GNOME Software / Ubuntu App Center)։ Առանց դրա խանութը հավելվածը չի
 * ճանաչում. ցույց է տալիս փաթեթի հում անունը («aiauto-desktop»), առանց նկարագրության,
 * և չի հասկանում՝ տեղադրվա՞ծ է, թե՞ ոչ (կոճակը մնում է «Install» տեղադրելուց հետո էլ)։
 * id-ն ու <launchable>-ը պետք է համընկնեն .desktop ֆայլի անվան հետ, այլապես կապը չի բռնվում։
 * Տեքստերը app.json-ից են՝ մեկ աղբյուր բոլոր պլատֆորմների համար։
 */
const esc = (v) => String(v).replace(/[<>&]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' })[c]);
const perLocale = (tag, texts) => Object.entries(texts)
    // Առաջինը լռելյայն (առանց xml:lang) անգլերենն է, մնացածը՝ թարգմանություններ
    .sort(([a]) => (a === 'en' ? -1 : 1))
    .map(([lang, text]) => `  <${tag}${lang === 'en' ? '' : ` xml:lang="${lang}"`}>${esc(text)}</${tag}>`)
    .join('\n');

const metainfo = path.join(__dirname, 'build', `${appId}.metainfo.xml`);
fs.writeFileSync(metainfo, `<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>${appId}</id>
  <name>${esc(cfg.name)}</name>
${perLocale('summary', summary)}
  <metadata_license>CC0-1.0</metadata_license>
  <project_license>LicenseRef-proprietary</project_license>
  <developer id="${new URL(cfg.url).hostname.split('.').reverse().join('.')}">
    <name>${esc(cfg.name)}</name>
  </developer>
  <description>
${perLocale('p', description).replace(/^ {2}/gm, '    ')}
  </description>
  <launchable type="desktop-id">aiauto.desktop</launchable>
  <url type="homepage">${esc(cfg.url)}</url>
  <categories>
    <category>Utility</category>
  </categories>
  <content_rating type="oars-1.1" />
  <releases>
    <release version="${version}" date="${new Date().toISOString().slice(0, 10)}" />
  </releases>
</component>
`);

module.exports = {
    appId,
    productName: cfg.name,
    // Վերսիան, կայքն ու հեղինակը package.json-ից չեն, այլ app.json-ից (մեկ աղբյուր բոլոր պլատֆորմների համար).
    // .deb-ը պահանջում է homepage և maintainer
    extraMetadata: {
        version,
        homepage: cfg.url,
        author: desktop.maintainer || 'AI Auto Service',
        // Linux-ի պատուհանը կապվում է .desktop գրառմանը (WM_CLASS)
        desktopName: 'aiauto.desktop',
    },
    directories: { output: path.join(__dirname, '..', 'out', 'desktop'), buildResources: path.join(__dirname, 'build') },
    // Կայքն ինքը սերվերի վրա է. փաթեթի մեջ գնում է միայն պատյանը + ընդհանուր կոնֆիգն ու offline էջը
    files: ['main.js', 'preload.js', 'package.json'],
    // to-ն resources/ թղթապանակի ներսում է. main.js-ը asar-ից նայում է հենց այնտեղ (__dirname/..)
    extraResources: [
        { from: path.join(__dirname, '..', 'app.json'), to: 'app.json' },
        { from: path.join(__dirname, '..', 'shared', 'error.html'), to: 'shared/error.html' },
        // Tray-ի պատկերակը (Windows/Linux). պատուհանը փակելիս հավելվածը մնում է այստեղ՝ զանգի հիշեցումների համար
        { from: path.join(__dirname, 'build', 'icons', '32x32.png'), to: 'tray.png' },
    ],
    win: {
        target: [{ target: 'nsis', arch: ['x64', 'arm64'] }],
        artifactName: '${productName}-${version}-setup-${arch}.${ext}',
    },
    nsis: {
        oneClick: false,
        allowToChangeInstallationDirectory: true,
        perMachine: false,
        deleteAppDataOnUninstall: false,
    },
    linux: {
        maintainer: desktop.maintainer || 'AI Auto Service',
        syncDesktopName: true,
        executableName: 'aiauto',
        target: [{ target: 'AppImage', arch: ['x64', 'arm64'] }, { target: 'deb', arch: ['x64', 'arm64'] }],
        category: 'Utility',
        // apt/dpkg-ի նկարագրությունը. խանութը վերցնում է AppStream-ից, տերմինալը՝ սրանից։
        // ՈՒՇԱԴՐՈՒԹՅՈՒՆ. electron-builder-ը .desktop-ի Comment-ը գրում է հենց description-ից
        // (entry.Comment-ը վերագրվում է), ուստի այստեղ երկար տեքստ չի կարելի՝ ամբողջը կընկնի Comment-ի մեջ
        synopsis: summary.en,
        description: summary.en,
        desktop: { entry: { Keywords: 'AI Auto Service;car;garage;service;auto;mechanic;' } },
        artifactName: '${productName}-${version}-${arch}.${ext}',
    },
    // metainfo-ն fpm-ին տրվում է որպես src=dest զույգ (electron-builder-ը իր ֆայլերը նույն ձևով է դնում)
    deb: { fpm: [`${metainfo}=/usr/share/metainfo/${appId}.metainfo.xml`] },
    mac: {
        target: [{ target: 'dmg', arch: ['x64', 'arm64'] }],
        category: 'public.app-category.utilities',
        artifactName: '${productName}-${version}-${arch}.${ext}',
        hardenedRuntime: true,
        entitlements: path.join(__dirname, 'build', 'entitlements.mac.plist'),
        entitlementsInherit: path.join(__dirname, 'build', 'entitlements.mac.plist'),
        // Տեսախցիկի/խոսափողի համակարգային հարցումների տեքստերը
        extendInfo: {
            NSCameraUsageDescription: 'Տեսախցիկը պետք է հայտին լուսանկար կցելու համար։',
            NSMicrophoneUsageDescription: 'Խոսափողը պետք է ձայնային հաղորդագրության համար։',
        },
    },
    dmg: { artifactName: '${productName}-${version}-${arch}.${ext}' },
};
