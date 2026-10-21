#!/usr/bin/env bash
# Run as the desktop user, NOT with sudo; only system changes request sudo.
set -euo pipefail

if (( EUID == 0 )); then
    echo 'Run this script as your desktop user, without sudo.' >&2
    exit 1
fi

base=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
runtime="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-gdm-wallpaper-sync"
for command in python gresource glib-compile-resources systemctl sudo; do
    command -v "$command" >/dev/null || { echo "Missing dependency: $command" >&2; exit 1; }
done
/usr/bin/python -I -c 'from gi.repository import Gio, GLib'
systemctl --user is-active --quiet graphical-session.target || {
    echo 'Install from a terminal inside your GNOME desktop session.' >&2
    exit 1
}

unit="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/gdm-wallpaper-sync.service"
helper=/usr/local/libexec/gdm-wallpaper-sync-theme
hook=/etc/pacman.d/hooks/95-gdm-wallpaper-sync.hook
state=/var/lib/gdm-wallpaper-sync

# Do not overwrite unrelated files using the same names.
for file in "$unit" "$helper" "$hook"; do
    if [[ -L "$file" ]]; then
        echo "Refusing to overwrite a symlink: $file" >&2
        exit 1
    fi
    if [[ -e "$file" ]] && ! grep -q 'gdm-wallpaper-sync' "$file"; then
        echo "Unrecognized existing file: $file" >&2
        exit 1
    fi
done
if [[ -L "$state" || -L "$state/wallpaper" ]]; then
    echo 'Refusing symlinked state/image directories.' >&2
    exit 1
fi
if [[ -L "$runtime" || -L "$runtime/sync-wallpaper.py" ]]; then
    echo 'Refusing a symlinked runtime directory or program.' >&2
    exit 1
fi
if [[ -e "$runtime/sync-wallpaper.py" ]] && ! grep -q 'Managed by gnome-gdm-wallpaper-sync' "$runtime/sync-wallpaper.py"; then
    echo "Refusing to overwrite an unrecognized runtime program: $runtime/sync-wallpaper.py" >&2
    exit 1
fi
if [[ ! -f /usr/share/gnome-shell/gnome-shell-theme.gresource ]]; then
    echo 'This installer requires the standard GNOME Shell theme resource layout; see PORTABILITY.md.' >&2
    exit 1
fi
style=$(/usr/bin/python -I "$base/sync-wallpaper.py" --print-style)
/usr/bin/python -I -c '
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("theme", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.validated_style(json.loads(sys.argv[2]))
' "$base/theme.py" "$style"

echo 'The last displayed wallpaper will be visible to anyone at the login screen.'
echo 'System setup requires sudo. GDM will NOT be restarted.'
sudo /usr/bin/install -d -o root -g root -m 0755 "$state"
sudo /usr/bin/install -d -o "$(id -u)" -g "$(id -g)" -m 0755 "$state/wallpaper"

# Seed as the unprivileged user, never by running gsettings as root.
/usr/bin/python -I "$base/sync-wallpaper.py" --once
sudo /usr/bin/install -D -o root -g root -m 0755 "$base/theme.py" "$helper"
sudo "$helper" apply --style "$style"
if command -v pacman >/dev/null; then
    sudo /usr/bin/install -D -o root -g root -m 0644 "$base/95-gdm-wallpaper-sync.hook" "$hook"
else
    echo 'No pacman detected: reapply the theme manually after GNOME Shell updates.'
fi
/usr/bin/install -D -m 0644 "$base/sync-wallpaper.py" "$runtime/sync-wallpaper.py"
/usr/bin/python -I "$base/render-unit.py" "$base/gdm-wallpaper-sync.service" "$runtime/sync-wallpaper.py" "$unit"
systemctl --user daemon-reload
systemctl --user enable gdm-wallpaper-sync.service
systemctl --user restart gdm-wallpaper-sync.service

echo 'Installed. Changes apply the next time GDM starts (logout or reboot).'
echo 'No display/HDR settings were changed, and your session was not restarted.'
