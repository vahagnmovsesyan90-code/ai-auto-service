'use strict';

/**
 * AI Auto Service-ի դեսկտոպ պատյանը (Electron)՝ Windows և macOS։ Կայքը բացվում է հավելվածի պատուհանում,
 * մնացած հղումները՝ համակարգի բրաուզերում։ Կոնֆիգը նույն ../app.json-ն է, ինչ Android-ի ու iOS-ի մոտ։
 * Ապահովում է՝ WebRTC (տեսախցիկ/խոսափող միայն մեր origin-ին), ֆայլի ընտրիչ ու ներբեռնումներ (համակարգայինը),
 * նավիգացիա (հետ/առաջ, գլխավոր), zoom, offline էջ, պատուհանի չափի հիշում, cookie-ներ/session։
 *
 * Զանգի հիշեցումներ (user, 2026-09-25). Electron-ում Web Push չկա, ուստի հիշեցումը գալիս է websocket-ով բաց էջին, և
 * էջը ցույց է տալիս համակարգային ծանուցում (Windows Action Center, macOS Notification Center, Linux)։ Որ փակ պատուհանի
 * դեպքում էլ գա, հիմնական պատուհանը «Փակել»-ով չի փակվում, այլ թաքնվում է (tray / macOS Dock), իսկ հավելվածը միանում է
 * համակարգի մեկնարկին (tray-ի ընտրացանկից կարելի է անջատել)։ Իսկական ելքը՝ tray → «Ելք» կամ Cmd+Q
 */

const { app, BrowserWindow, Menu, Tray, ipcMain, nativeImage, session, shell, systemPreferences } = require('electron');
const fs = require('node:fs');
const path = require('node:path');

const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'app.json'), 'utf8'));
// Փաթեթավորված build-ը գնում է production հասցեին, աղբյուրից գործարկելը՝ dev սերվերին։
// Դրոշները ստիպում են՝ --dev կամ --prod (npm run start:prod-ը production հասցեն ստուգելու համար է)։
// 10.0.2.2-ը Android emulator-ի հասցեն է, դեսկտոպում նույնն է՝ localhost։
const dev = process.argv.includes('--dev') || (!app.isPackaged && !process.argv.includes('--prod'));
const startUrl = dev ? String(cfg.devUrl).replace('10.0.2.2', 'localhost') : cfg.url;
const allowedHosts = new Set(dev ? [...cfg.hosts, ...cfg.devHosts] : cfg.hosts);
const errorPage = path.join(__dirname, '..', 'shared', 'error.html');
const stateFile = () => path.join(app.getPath('userData'), 'window.json');

// Կայքը կարող է ճանաչել հավելվածը (նույն վերջածանցը, ինչ բջջայինում)
app.userAgentFallback = `${app.userAgentFallback} ${cfg.userAgentSuffix}`;
// Անունը app.json-ից է, որ dev-ում ու փաթեթում userData-ի ուղին նույնը լինի
app.setName(cfg.name);

/** Մերոնք են բացվում պատուհանում. մնացածը՝ բրաուզերում (tel:, mailto:, ուրիշ կայք) */
const isAllowed = (url) => {
    try {
        const u = new URL(url);

        return (u.protocol === 'https:' || u.protocol === 'http:') && allowedHosts.has(u.hostname.toLowerCase());
    } catch {
        return false;
    }
};

/** Պատուհանի վերջին չափն ու տեղը (userData/window.json). կոտրված ֆայլը պարզապես անտեսվում է */
const readState = () => {
    try {
        const s = JSON.parse(fs.readFileSync(stateFile(), 'utf8'));

        return typeof s.width === 'number' && typeof s.height === 'number' ? s : {};
    } catch {
        return {};
    }
};

const saveState = (win) => {
    if (win.isDestroyed() || win.isMinimized()) return;
    const { x, y, width, height } = win.getNormalBounds();
    try {
        fs.writeFileSync(stateFile(), JSON.stringify({ x, y, width, height, maximized: win.isMaximized() }));
    } catch {}
};

const windows = new Set();
let mainWindow = null;
let tray = null;
// Իսկական ելք (tray → «Ելք», Cmd+Q, համակարգի անջատում). մնացած դեպքում հիմնական պատուհանը միայն թաքնվում է
let quitting = false;
app.on('before-quit', () => { quitting = true; });

/** Հիմնական պատուհանը ցույց տալ (tray-ից, ծանուցումից, երկրորդ գործարկումից). path՝ կայքի ներսի ուղի */
function showMain(pathname) {
    let win = mainWindow;
    if (!win || win.isDestroyed()) win = mainWindow = createWindow(startUrl, readState());
    if (win.isMinimized()) win.restore();
    win.show();
    win.focus();
    if (typeof pathname === 'string' && pathname.startsWith('/') && !pathname.startsWith('//')) {
        win.loadURL(new URL(pathname, startUrl).href);
    }
}

function createWindow(url = startUrl, state = {}, { hidden = false } = {}) {
    const win = new BrowserWindow({
        x: state.x,
        y: state.y,
        width: state.width || 1280,
        height: state.height || 860,
        minWidth: 880,
        minHeight: 600,
        title: cfg.name,
        backgroundColor: '#F4F6F5',
        show: false,
        webPreferences: {
            // Կայքի կոդը հավելվածի ոչ մի API չի տեսնում. պատյանը միայն «պատուհան» է
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: true,
            spellcheck: true,
            preload: path.join(__dirname, 'preload.js'),
            // Թաքնված պատուհանում էլ websocket-ը և ժամաչափերը չեն դանդաղեցվում՝ հիշեցումը ժամանակին է գալիս
            backgroundThrottling: false,
        },
    });
    windows.add(win);
    if (state.maximized) win.maximize();

    // Վերջին հասցեն՝ offline էջից «Փորձել նորից»-ի համար
    let lastUrl = url;

    win.once('ready-to-show', () => { if (!hidden) win.show(); });
    win.on('close', (e) => {
        saveState(win);
        // Հիմնական պատուհանը թաքնվում է (հիշեցումները շարունակում են գալ), եթե իսկական ելք չէ
        if (win === mainWindow && !quitting) {
            e.preventDefault();
            win.hide();
        }
    });
    win.on('closed', () => windows.delete(win));

    const wc = win.webContents;

    wc.on('page-title-updated', (e) => e.preventDefault());

    // Կայքից դուրս հղումը՝ համակարգի բրաուզեր. app://retry-ն offline էջի կոճակն է
    wc.on('will-navigate', (e, next) => {
        if (next.startsWith('app://retry')) {
            e.preventDefault();
            win.loadURL(lastUrl);

            return;
        }
        if (isAllowed(next)) {
            lastUrl = next;

            return;
        }
        e.preventDefault();
        shell.openExternal(next);
    });

    // target=_blank. մերը՝ նոր պատուհանում, ուրիշը՝ բրաուզերում
    wc.setWindowOpenHandler(({ url: next }) => {
        if (isAllowed(next)) createWindow(next);
        else shell.openExternal(next);

        return { action: 'deny' };
    });

    // Ինտերնետ չկա / սերվերը չի պատասխանում → offline էջ (ERR_ABORTED-ը սովորական ընդհատում է)
    wc.on('did-fail-load', (e, code, desc, failedUrl, isMainFrame) => {
        if (!isMainFrame || code === -3) return;
        if (failedUrl && isAllowed(failedUrl)) lastUrl = failedUrl;
        win.loadFile(errorPage);
    });

    win.loadURL(url);

    return win;
}

/** Տեսախցիկ/խոսափող (և լիաէկրան) միայն մեր կայքին. մնացած հարցումները մերժվում են */
function guardPermissions(ses) {
    // notifications՝ զանգի հիշեցման համակարգային ծանուցումը (front/src/push.js)
    const allowedPermissions = new Set(['media', 'fullscreen', 'clipboard-sanitized-write', 'pointerLock', 'notifications']);

    ses.setPermissionRequestHandler((wc, permission, callback, details) => {
        const origin = details?.requestingUrl || wc?.getURL() || '';
        const ok = allowedPermissions.has(permission) && isAllowed(origin);
        // macOS-ում համակարգն էլ է թույլտվություն ուզում (Համակարգի կարգավորումներ → Գաղտնիություն)
        if (ok && permission === 'media' && process.platform === 'darwin') {
            const kinds = details?.mediaTypes?.length ? details.mediaTypes : ['audio', 'video'];
            Promise.all(kinds.map((k) => systemPreferences.askForMediaAccess(k === 'video' ? 'camera' : 'microphone')))
                .then((results) => callback(results.every(Boolean)))
                .catch(() => callback(false));

            return;
        }
        callback(ok);
    });

    ses.setPermissionCheckHandler((wc, permission, origin) => allowedPermissions.has(permission) && isAllowed(origin || ''));
}

/** Tray-ի պատկերակը (Windows/Linux). macOS-ում հավելվածը մնում է Dock-ում, tray պետք չէ */
function buildTray() {
    if (process.platform === 'darwin') return;
    const icon = [path.join(__dirname, '..', 'tray.png'), path.join(__dirname, 'build', 'icons', '32x32.png')].find((p) => fs.existsSync(p));
    if (!icon) return;
    tray = new Tray(nativeImage.createFromPath(icon));
    tray.setToolTip(cfg.name);
    const refresh = () => tray.setContextMenu(Menu.buildFromTemplate([
        { label: 'Բացել AI Auto Service-ը', click: () => showMain() },
        { type: 'separator' },
        {
            label: 'Գործարկել համակարգի հետ (ծանուցումների համար)',
            type: 'checkbox',
            checked: app.getLoginItemSettings().openAtLogin,
            click: (item) => { app.setLoginItemSettings({ openAtLogin: item.checked, args: ['--hidden'] }); refresh(); },
        },
        { type: 'separator' },
        { label: 'Ելք', click: () => { quitting = true; app.quit(); } },
    ]));
    refresh();
    tray.on('click', () => showMain());
}

/** Առաջին գործարկմանը հավելվածը միանում է համակարգի մեկնարկին (թաքնված), որ հիշեցումները գան։ Հետո՝ օգտատիրոջ ընտրությունը */
function autoStartOnce() {
    if (dev) return;
    const flag = path.join(app.getPath('userData'), 'autostart.json');
    if (fs.existsSync(flag)) return;
    try {
        app.setLoginItemSettings({ openAtLogin: true, openAsHidden: true, args: ['--hidden'] });
        fs.writeFileSync(flag, '{"set":true}');
    } catch {}
}

function buildMenu() {
    const mac = process.platform === 'darwin';
    const focused = () => BrowserWindow.getFocusedWindow();
    const template = [
        ...(mac ? [{ role: 'appMenu' }] : []),
        {
            label: 'Ֆայլ',
            submenu: [
                { label: 'Նոր պատուհան', accelerator: 'CmdOrCtrl+N', click: () => createWindow() },
                { type: 'separator' },
                mac ? { role: 'close', label: 'Փակել' } : { role: 'quit', label: 'Ելք' },
            ],
        },
        { role: 'editMenu', label: 'Խմբագրում' },
        {
            label: 'Դիտել',
            submenu: [
                { label: 'Թարմացնել', accelerator: 'CmdOrCtrl+R', click: () => focused()?.webContents.reload() },
                { type: 'separator' },
                { label: 'Հետ', accelerator: mac ? 'Cmd+[' : 'Alt+Left', click: () => focused()?.webContents.navigationHistory.goBack() },
                { label: 'Առաջ', accelerator: mac ? 'Cmd+]' : 'Alt+Right', click: () => focused()?.webContents.navigationHistory.goForward() },
                { label: 'Գլխավոր էջ', accelerator: 'CmdOrCtrl+Shift+H', click: () => focused()?.loadURL(startUrl) },
                { type: 'separator' },
                { role: 'resetZoom', label: 'Սովորական չափ' },
                { role: 'zoomIn', label: 'Խոշորացնել' },
                { role: 'zoomOut', label: 'Մանրացնել' },
                { type: 'separator' },
                { role: 'togglefullscreen', label: 'Լիաէկրան' },
                ...(dev ? [{ role: 'toggleDevTools' }] : []),
            ],
        },
        { role: 'windowMenu', label: 'Պատուհան' },
    ];

    Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// Մեկ օրինակ. երկրորդ գործարկումը բացում է արդեն բացվածը
if (!app.requestSingleInstanceLock()) {
    app.quit();
} else {
    app.on('second-instance', () => showMain());

    // Էջի ծանուցման սեղմումը (preload.js → aaDesktop.show)
    ipcMain.on('aa:show', (e, pathname) => showMain(pathname));

    app.whenReady().then(() => {
        guardPermissions(session.defaultSession);
        buildMenu();
        buildTray();
        // Համակարգի մեկնարկին ավտոմատ միացում չկա. օգտատերը ինքն է միացնում tray-ի ընտրացանկից
        // Windows-ում ծանուցումները ցույց են տրվում միայն AppUserModelID-ով (installer-ի դյուրանցման հետ նույնը)
        if (process.platform === 'win32') app.setAppUserModelId(cfg.desktop?.appId || 'am.aiauto.desktop');
        // Համակարգի մեկնարկից (--hidden կամ macOS-ի openAsHidden)՝ պատուհանը թաքնված է, էջը բեռնվում է և լսում է հիշեցումները
        const hidden = process.argv.includes('--hidden') || app.getLoginItemSettings().wasOpenedAsHidden;
        mainWindow = createWindow(startUrl, readState(), { hidden });

        // macOS. Dock-ի պատկերակից՝ հիմնական պատուհանը
        app.on('activate', () => showMain());
    });

    app.on('window-all-closed', () => {
        if (process.platform !== 'darwin') app.quit();
    });
}
