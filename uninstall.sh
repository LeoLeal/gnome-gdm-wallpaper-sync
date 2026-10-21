#!/usr/bin/env bash
set -euo pipefail

if (( EUID == 0 )); then
    echo 'Run this script as your desktop user, without sudo.' >&2
    exit 1
fi

unit="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/gdm-wallpaper-sync.service"
helper=/usr/local/libexec/gdm-wallpaper-sync-theme
hook=/etc/pacman.d/hooks/95-gdm-wallpaper-sync.hook

for file in "$unit" "$helper" "$hook"; do
    if [[ -L "$file" ]] || { [[ -e "$file" ]] && ! grep -q 'gdm-wallpaper-sync' "$file"; }; then
        echo "Unrecognized file; refusing to remove it: $file" >&2
        exit 1
    fi
done

if [[ -f "$unit" ]]; then
    systemctl --user disable --now gdm-wallpaper-sync.service
fi
if [[ -f "$helper" ]]; then
    sudo "$helper" restore
fi
for file in "$hook" "$helper"; do
    if [[ -f "$file" ]]; then
        sudo /usr/bin/rm -- "$file"
    fi
done
if [[ -f "$unit" ]]; then
    /usr/bin/rm -- "$unit"
fi
systemctl --user daemon-reload
echo 'Uninstalled without restarting GDM. Theme backups and the saved image remain in /var/lib/gdm-wallpaper-sync.'
