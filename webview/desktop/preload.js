'use strict';

/**
 * Էջին տրվող միակ կամուրջը. զանգի հիշեցման ծանուցումը սեղմելիս (front/src/push.js) պատուհանը
 * հետ է բերվում tray-ից և անցնում ծանուցման էջին։ Ուրիշ ոչինչ հասանելի չէ (contextIsolation + sandbox)
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('aaDesktop', {
    show: (path) => ipcRenderer.send('aa:show', typeof path === 'string' ? path : null),
});
