# GNOME–GDM Wallpaper Sync

Use the most recently displayed GNOME wallpaper on the GDM login screen.
Event-driven, with no polling or persistent root daemon. Works with standard
GNOME Appearance settings and wallpaper extensions that update the same settings.

**Experimental and unofficial.**

**Tested environment:** CachyOS (Arch Linux), using GDM and GNOME 51.

This modifies a system GNOME Shell theme resource. Read [PORTABILITY.md](PORTABILITY.md)
before installing; other distribution/theme layouts are not automatically supported.
This project is not affiliated with GNOME.

## Requirements

- Linux, systemd user sessions, GNOME Shell and GDM.
- System Python with PyGObject, Gio, GLib and GLibUnix introspection data.
- GNOME desktop GSettings schemas, `shared-mime-info` (for image detection),
  `gresource`, `glib-compile-resources`, Bash, GNU coreutils and sudo.
- A regular resource file at `/usr/share/gnome-shell/gnome-shell-theme.gresource`
  containing the `#lockDialogGroup` CSS selector.

On Arch Linux the development/test dependencies can be installed with:

```bash
sudo pacman -S --needed python python-gobject glib2-devel gsettings-desktop-schemas shared-mime-info dbus
```

## Install

From this checkout, in a terminal inside the GNOME desktop, run **without sudo**:

```bash
bash ./install.sh
```

The installer requests sudo for the system setup, backs up the theme, captures
the current wallpaper sizing/colors, and installs a runtime copy under
`${XDG_DATA_HOME:-$HOME/.local/share}/gnome-gdm-wallpaper-sync`. The checkout can
be kept anywhere. It installs a user unit under the XDG config directory and
does **not** restart GDM, log out the session or modify display/HDR settings.

Save work and log out when ready to test. The last image is loaded when a new
greeter starts, not continuously refreshed in an already-visible greeter.

## Behavior and privacy

- Watches GNOME's `picture-uri`, `picture-uri-dark` and color-scheme settings.
- Atomically copies the active image to
  `/var/lib/gdm-wallpaper-sync/wallpaper/current`, preserving its original bytes.
- A small CSS override makes GDM load that external image. Other resource entries
  are preserved and verified before replacing the system resource.
- Supports local static images; not videos, remote URLs, GNOME XML slideshows,
  or spanned multi-monitor wallpapers. No crossfade or lock-screen customization.
- **The cached image is public to local users and anyone viewing the login screen.**
  Only use wallpapers you are comfortable exposing there.
- One designated desktop user controls the machine-wide GDM background. This
  installer is not a multi-user wallpaper arbitration system.

The service sleeps between changes and runs at idle CPU/I/O priority. It does
not decode, resize or recompress images, rebuild themes on each change, or force
disk flushes on slide changes. A sudden power loss may lose the latest cache
update. Low priority is not a zero-stutter guarantee: pause wallpaper slideshows
while gaming if frame-time consistency is critical. The service itself does not
detect fullscreen games or require a particular slideshow extension.

## Updates and troubleshooting

```bash
systemctl --user status gdm-wallpaper-sync.service
journalctl --user -u gdm-wallpaper-sync.service -n 30 --no-pager
```

On pacman systems, an optional package hook reapplies the CSS after GNOME Shell
updates. Without pacman, or after applying a theme through GDM Settings, run:

```bash
sudo /usr/local/libexec/gdm-wallpaper-sync-theme apply
```

Changing the image is automatic. Changing desktop Zoom/cropping, background
color or shading requires rerunning `bash ./install.sh` to capture the new style.
Future GNOME changes may require adapting the resource patcher.

## Uninstall

```bash
bash ./uninstall.sh
```

This stops the watcher and removes its unit, helper and package hook. It restores
the exact pre-patch resource when safe, or removes only its own CSS if there have
been newer theme customizations. It does not restart GDM. Backups, the runtime
copy and cached image are retained. To also remove the public image afterwards:

```bash
rm -- /var/lib/gdm-wallpaper-sync/wallpaper/current
```

## Development

```bash
python -B -m unittest -v test_sync.py
bash -n install.sh uninstall.sh
```

Tests use synthetic image/resources and normal temporary directories (respecting
`TMPDIR`). They do not patch the installed theme, run the installer, restart
services or change real wallpaper preferences. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE). System GNOME assets are not bundled or relicensed by this project.
