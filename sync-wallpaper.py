#!/usr/bin/python
# Managed by gnome-gdm-wallpaper-sync
"""Keep a public, atomic copy of the active GNOME wallpaper for the next greeter."""

import argparse
import json
import logging
import os
from pathlib import Path
import signal
import stat
import tempfile

import gi
gi.require_version('GLibUnix', '2.0')
from gi.repository import Gio, GLib, GLibUnix


DEFAULT_DIRECTORY = Path('/var/lib/gdm-wallpaper-sync/wallpaper')
MAX_IMAGE_BYTES = 128 * 1024 * 1024


def copy_wallpaper(uri, directory):
    """Copy local files without interpreting a settings value as shell code."""
    source = Gio.File.new_for_uri(uri)
    path = source.get_path()
    if source.get_uri_scheme() != 'file' or not path:
        raise ValueError('The wallpaper must be a local file URI')

    temporary = None
    try:
        # O_NONBLOCK lets us reject a FIFO rather than hanging on open().
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as image:
            info = os.fstat(image.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('The wallpaper is not a regular file')
            if not 0 < info.st_size <= MAX_IMAGE_BYTES:
                raise ValueError('The wallpaper is empty or exceeds 128 MiB')
            header = image.read(4096)
            content_type, _ = Gio.content_type_guess(path, header)
            if not content_type or not content_type.startswith('image/'):
                raise ValueError('The wallpaper is not a supported image file')
            image.seek(0)

            with tempfile.NamedTemporaryFile(
                dir=directory, prefix='.current-', delete=False
            ) as output:
                temporary = Path(output.name)
                copied = 0
                while chunk := image.read(1024 * 1024):
                    copied += len(chunk)
                    if copied > MAX_IMAGE_BYTES:
                        raise ValueError('The wallpaper exceeds 128 MiB')
                    output.write(chunk)
                if copied == 0:
                    raise ValueError('The wallpaper became empty while copying')
                os.fchmod(output.fileno(), 0o644)
                output.flush()
                # Let the kernel write this cache back normally. Forcing a disk
                # flush on each slide can compete with game/asset I/O. Atomic
                # replacement still prevents GDM from seeing a partial image.

        destination = directory / 'current'
        os.replace(temporary, destination)
        temporary = None
        logging.info('Saved %s for the next GDM login', path)
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def active_uri(background, interface):
    key = ('picture-uri-dark' if interface.get_string('color-scheme') == 'prefer-dark'
           else 'picture-uri')
    return background.get_string(key) or background.get_string('picture-uri')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--print-style', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    background = Gio.Settings.new('org.gnome.desktop.background')
    interface = Gio.Settings.new('org.gnome.desktop.interface')

    if args.print_style:
        print(json.dumps({key: background.get_string(key) for key in (
            'picture-options', 'color-shading-type', 'primary-color', 'secondary-color'
        )}))
        return 0

    if not args.directory.is_dir() or not os.access(args.directory, os.W_OK):
        parser.error(f'{args.directory} must exist and be writable; run install.sh first')

    def sync():
        try:
            copy_wallpaper(active_uri(background, interface), args.directory)
            return True
        except (OSError, ValueError, GLib.Error) as error:
            # Never remove the last working image on an invalid/missing new one.
            logging.warning('Keeping the previous wallpaper: %s', error)
            return False

    initial_ok = sync()
    if args.once:
        return 0 if initial_ok else 1

    loop = GLib.MainLoop()
    pending = 0

    def flush():
        nonlocal pending
        pending = 0
        sync()
        return GLib.SOURCE_REMOVE

    def changed(*_):
        nonlocal pending
        if pending:
            GLib.source_remove(pending)
        # The slideshow changes light/dark URIs together; copy just once.
        pending = GLib.timeout_add(200, flush)

    background.connect('changed::picture-uri', changed)
    background.connect('changed::picture-uri-dark', changed)
    interface.connect('changed::color-scheme', changed)

    def stop():
        if pending:
            GLib.source_remove(pending)
        sync()
        loop.quit()
        return GLib.SOURCE_REMOVE

    for signum in (signal.SIGTERM, signal.SIGINT):
        GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signum, stop)
    loop.run()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
