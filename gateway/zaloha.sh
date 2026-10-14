#!/bin/bash
# Noční šifrovaná záloha brány. Pouští ji claude-hub-zaloha.timer (viz
# gateway/install.sh) jako root, jednou denně.
#
# Zálohuje se /home/hub — domovy prostorů (Obsidian, projekty), firemní vault
# a databáze účtů. Cache se vynechávají: jsou to gigabajty, které se stáhnou
# znovu, a obnovu by jen zdržely.
#
# ŠIFRUJE SE VEŘEJNÝM KLÍČEM. Server má jen ten veřejný, takže zálohu umí
# zabalit, ale rozbalit ne — a nepotřebuje k tomu žádné heslo. Soukromý klíč
# patří mimo server (u správce v trezoru hesel). Kdo ukradne server i se
# zálohami, nepřečte z nich nic.
#
# Klíč se nasadí jednou:
#     gpg --armor --export <klíč> | ssh root@brána 'cat > /etc/claude-hub/zalohy.asc'
#
# Bez toho souboru se záloha neudělá a jen to řekne — radši žádná záloha než
# nešifrovaná, která by ležela na disku a tvářila se, že je o co opřít.
#
# Obnova (na stroji, kde je soukromý klíč):
#     gpg -d hub-RRRRMMDD.tar.zst.gpg | zstd -d | tar -xf - -C /kam
#
# Ručně: claude-hub-zaloha
set -uo pipefail

KEY=/etc/claude-hub/zalohy.asc
DEST=/var/backups/claude-hub
SRC=/home/hub
KEEP=${HUB_ZALOHA_KEEP:-14}          # kolik denních záloh se drží
LOG=/var/log/claude-hub-zaloha.log

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >>"$LOG"; }

main() {
    if [ ! -s "$KEY" ]; then
        log "CHYBA: chybí veřejný klíč $KEY — záloha se nedělá (nešifrovanou dělat nebudu)"
        echo "Chybí $KEY. Nasaď veřejný klíč, jinak se zálohovat nebude." >&2
        exit 1
    fi
    mkdir -p "$DEST"
    chmod 700 "$DEST"

    local stamp out tmp
    stamp="$(date +%Y%m%d-%H%M)"
    out="$DEST/hub-$stamp.tar.zst.gpg"
    tmp="$out.part"

    # Vlastní klíčenka v /etc: root nemá mít v ~/.gnupg nic, co sem nepatří,
    # a --trust-model always kvůli tomu, že klíč nikdo nepodepsal.
    local ring=/etc/claude-hub/zalohy-gnupg
    mkdir -p "$ring"; chmod 700 "$ring"
    GNUPGHOME="$ring" gpg --batch --quiet --import "$KEY" 2>/dev/null

    local recipient
    recipient="$(GNUPGHOME="$ring" gpg --batch --with-colons --list-keys 2>/dev/null \
                 | awk -F: '/^uid/{print $10; exit}')"
    if [ -z "$recipient" ]; then
        log "CHYBA: klíč $KEY se nepodařilo načíst"
        exit 1
    fi

    # Místo pro novou zálohu: bude zhruba jako poslední (+10 %). Úklid by po
    # ní stejně nechal jen KEEP-1 starých — když se nevejde, smažou se ty
    # navíc už teď, ne až po ní (jinak by na disku musely být KEEP+1 kusy).
    # Poslední dobrou zálohu nikdy předem nemaže: kdyby nová selhala, nezbyla
    # by žádná.
    local last need free f
    last="$(ls -1t "$DEST"/hub-*.tar.zst.gpg 2>/dev/null | head -n 1)"
    if [ -n "$last" ]; then
        need=$(( $(stat -c %s "$last") * 11 / 10 ))
        while read -r f; do
            [ -n "$f" ] || continue
            free="$(df --output=avail -B1 "$DEST" | tail -n 1)"
            [ "$free" -gt "$need" ] && break
            rm -f "$f"
            log "kvůli místu předem smazána starší záloha: $(basename "$f")"
        done <<<"$(ls -1t "$DEST"/hub-*.tar.zst.gpg 2>/dev/null | tail -n +$((KEEP > 1 ? KEEP : 2)) | tac)"
        free="$(df --output=avail -B1 "$DEST" | tail -n 1)"
        if [ "$free" -le "$need" ]; then
            log "VAROVÁNÍ: na disku je $((free / 1024 / 1024)) MB, záloha bude mít asi $((need / 1024 / 1024)) MB — zkouším i tak"
        fi
    fi

    log "začínám (příjemce: $recipient)"
    # nice/ionice: na stroji zároveň pracují lidé, záloha jim nesmí ubrat výkon.
    # Vynechané cesty jsou cache (stáhnou se znovu) a koše po smazaných účtech.
    nice -n 19 ionice -c3 tar -C "$(dirname "$SRC")" -cf - \
            --warning=no-file-changed --warning=no-file-ignored \
            --exclude='*/.cache' \
            --exclude='*/.npm' \
            --exclude='*/.local/share/uv' \
            --exclude='*/.cache/ms-playwright' \
            --exclude='*/node_modules' \
            --exclude='*/.claude/projects/*/[0-9a-f]*.jsonl.bak' \
            --exclude='users/_smazany-*' \
            "$(basename "$SRC")" 2>>"$LOG" \
        | nice -n 19 zstd -3 -T2 -q \
        | GNUPGHOME="$ring" gpg --batch --yes --quiet --trust-model always \
              --encrypt --recipient "$recipient" --output "$tmp"
    local st=("${PIPESTATUS[@]}")
    # tar vrací 1, i když se jen soubor změnil během čtení — u živého serveru
    # běžné a záloha je použitelná. Chyba zstd nebo gpg (třeba plný disk) ale
    # znamená useknutý soubor: ten se nesmí tvářit jako záloha.
    if [ "${st[1]}" -eq 0 ] && [ "${st[2]}" -eq 0 ] && [ "${st[0]}" -le 1 ] && [ -s "$tmp" ]; then
        mv -f "$tmp" "$out"
        chmod 600 "$out"
        if [ "${st[0]}" -eq 0 ]; then
            log "hotovo: $(basename "$out") ($(du -h "$out" | cut -f1))"
        else
            log "hotovo s výhradou (soubor se měnil během čtení): $(basename "$out") ($(du -h "$out" | cut -f1))"
        fi
    else
        rm -f "$tmp"
        log "CHYBA: záloha se nepovedla (tar ${st[0]}, zstd ${st[1]}, gpg ${st[2]}; volno $(df -h "$DEST" | awk 'NR==2{print $4}')), nic jsem nezapsal"
        exit 1
    fi

    # Úklid: drží se posledních KEEP kusů.
    local old
    old="$(ls -1t "$DEST"/hub-*.tar.zst.gpg 2>/dev/null | tail -n +$((KEEP + 1)))"
    if [ -n "$old" ]; then
        echo "$old" | xargs -r rm -f
        log "smazáno starých záloh: $(echo "$old" | wc -l)"
    fi
    log "volno na disku: $(df -h "$DEST" | awk 'NR==2{print $4}')"
}

main "$@"
