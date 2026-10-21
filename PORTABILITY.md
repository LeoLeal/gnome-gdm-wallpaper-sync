# Portability and publishing audit

## Setup-specific assumptions removed

- No username, home-directory path, hostname, wallpaper filename or real image
  is included. Runtime caches, theme backups and compiled resources were not copied.
- The installer no longer requires the checkout to live in a particular runtime
  directory. It installs a separate watcher copy and renders a quoted user unit.
- XDG data/config locations are honored for the user installation.
- Tests use normal temporary directories and respect `TMPDIR`, rather than a
  coding-harness-only directory.
- Fallback styling is neutral; installation explicitly captures the user's real
  desktop style rather than shipping a particular user's background color.
- No slideshow-extension dependency or assumption that fullscreen pausing is
  already enabled remains. Only standard GNOME settings are watched.
- The package hook is installed only when pacman is available.

## Intentional platform limitations still present

1. Linux/systemd and modern GNOME/GDM are required. There is no SDDM, LightDM,
   non-systemd, macOS or Windows integration.
2. The theme helper expects the standard resource path
   `/usr/share/gnome-shell/gnome-shell-theme.gresource` and `#lockDialogGroup`
   selectors. Distro-specific resources such as alternate theme layouts need
   a packaging/code adaptation; they are not automatically discovered.
3. System executable paths use the Arch-style `/usr/bin/python`, `/usr/bin/gresource`
   and `/usr/bin/glib-compile-resources`. A distro without those paths needs an
   adapted package. PyGObject/GLibUnix and the desktop schemas must be installed.
4. The greeter background is machine-wide and managed by one designated owner.
   Installing for another user is not a supported arbitration mechanism.
5. Without pacman, theme updates require manual reapplication or an external
   distro-specific package hook. Changes applied by another theme tool may
   overwrite this override too.
6. Only local static images up to 128 MiB are cached; no XML/video/remote
   wallpapers or spanned monitor backgrounds. Styles/colors are captured at
   installation, not automatically synchronized on later style changes.
7. The copied image is deliberately public, and buffered writes do not guarantee
   the last update survives an abrupt power loss. Idle priority cannot guarantee
   stutter-free gaming or enforce I/O priority on every storage scheduler.

These are deployment requirements, not dependencies on a specific person's
computer. The project should not be presented as distribution-agnostic or as an
official/supported GNOME customization API.

The extracted public checkout has automated tests and unit-format checks, but
was not installed over the development machine's running services during this
audit. A fresh install/uninstall should be manually validated on a disposable
or recoverable GNOME/GDM system before tagging a release.
