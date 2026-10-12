/* Zavření okna, když hub drží beforeunload (Claude pracuje) — bez Playwrightu,
 * ten dialogy zachytává sám a nativní chování Electronu by se neprojevilo.
 * Spouští ho smoke.mjs: electron test/zavreni.cjs (s proměnnými jako appka). */
const { app } = require('electron');
const fs = require('fs');
const out = process.env.HUB_ZAVRENI_VYSLEDEK;
require('../main.js');
app.on('browser-window-created', (_e, win) => {
  win.webContents.once('did-finish-load', async () => {
    await new Promise((r) => setTimeout(r, 2000));
    // S gestem: beforeunload bez interakce uživatele Chromium nebere.
    await win.webContents.executeJavaScript(
      "addEventListener('beforeunload', (e) => { e.preventDefault(); e.returnValue = ''; }); 1", true);
    // Zavřené okno ukončí appku (poslední okno) — výsledek se zapíše hned.
    win.once('closed', () => fs.writeFileSync(out, JSON.stringify({ zavreno: true })));
    win.close();
    setTimeout(() => {
      if (!win.isDestroyed()) { fs.writeFileSync(out, JSON.stringify({ zavreno: false })); app.exit(0); }
    }, 4000);
  });
});
