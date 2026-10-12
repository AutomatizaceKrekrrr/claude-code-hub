# Claude Code Hub — samostatná aplikace (desktop/)

Okno hubu jako skutečná aplikace, stejně jako VS Code: v liště **Claude Code Hub**
místo „Chrome", vlastní menu a **Cmd/Ctrl+N otevře další okno hubu** (ne prázdný
Chrome). Postavené na [Electronu](https://www.electronjs.org/) — stejné jádro
(Chromium), na kterém hub běží dnes, a stejné UI. Nic se nepřepisuje.

## Jak to funguje

- Appka najde **nainstalovaný hub** (`~/.claude/claude-hub.py`, Python z
  `~/.claude/runtime/python`, jinak systémový) a spustí ho s `--vlastni-okno`:
  hub jen vypíše adresu a žije, dokud je otevřená aspoň jedna stránka — pak se
  ukončí jako dřív. Aktualizace hubu tedy fungují beze změny.
- **Hub už běží** (`hub-bezi.json`)? Appka se k němu jen připojí — druhá
  instance nad týmiž chaty by si přepisovala konverzace.
- **Starší hub**, který `--vlastni-okno` nezná, se spustí s `--no-browser`
  a appka ho při ukončení zavře sama.
- **Nové okno** (Cmd/Ctrl+N, Soubor → Nové okno) = další okno téhož hubu.
  Okna sdílejí taby, každé má aktivní jiný — třeba jeden chat na monitor.
- **Aktualizace hubu za běhu**: hub přejde na nový port, okna se přepnou sama
  a nová okna jdou rovnou tam.
- Odkazy a cizí stránky jdou do systémového prohlížeče. Okno ukazuje jen
  lokální hub (`127.0.0.1`) a prostor na serveru z nastavení (`gw_server`).
- Mikrofon (diktování), schránka a upozornění jsou povolené jen hubu.

## Vývoj a zkouška

```bash
cd desktop
npm install
npm start          # appka nad nainstalovaným hubem
npm test           # zkouška: 4 scénáře se skutečným hubem z repa
```

Zkouška (`test/smoke.mjs`) používá hub z repa a dočasnou konfiguraci
(`CLAUDE_CONFIG_DIR`), takže nesahá na nainstalovaný hub ani na `~/.claude`.
Projde: okno a menu, Nové okno + sdílené taby, odkazy ven, konec oken = konec
hubu; připojení k běžícímu hubu; starší hub bez přepínače; aktualizaci za běhu.
Linux bez displeje: `xvfb-run -a npm test`. Zabalená appka:
`HUB_DESKTOP_EXE=<spustitelný soubor> npm test`.

## Instalačky

```bash
npm run dist       # pro systém, na kterém běží (dmg+zip / Setup.exe / AppImage)
```

GitHub Actions (`.github/workflows/desktop.yml`) je postaví na Windows, Linuxu
a macOS (Apple Silicon i Intel) a každou zabalenou appku otestují stejnou
zkouškou. Appky nejsou podepsané certifikátem: Mac (ad-hoc podpis jako
`packaging/mac/build.sh`) je poprvé pustí až Nastavení systému → Soukromí
a zabezpečení → Přesto otevřít, Windows ukáže SmartScreen („Další informace →
Přesto spustit").

## Co zatím není

- Spojení s instalačkami v `packaging/` (aby `.dmg`/Setup.exe rovnou nesly tuhle
  appku místo okna Chromu) — rozhodnutí pro správce repa.
- Podpis certifikátem (Apple Developer, Windows code signing).
- Samoaktualizace appky — hub uvnitř se aktualizuje sám jako dřív, ale novou
  verzi samotné appky (`desktop/`) je potřeba stáhnout znovu.
