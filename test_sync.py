"""Local-only tests: never touch the installed theme, settings, or services."""

import base64
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


# Keep test file operations local; never auto-activate desktop GVfs services.
os.environ.setdefault('GIO_USE_VFS', 'local')
DIRECTORY = Path(__file__).resolve().parent


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, DIRECTORY / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync = load_module('wallpaper_sync', 'sync-wallpaper.py')
theme = load_module('wallpaper_theme', 'theme.py')
units = load_module('wallpaper_unit', 'render-unit.py')
PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aH9sAAAAASUVORK5CYII='
)
CSS_NAME = '/org/gnome/shell/theme/gnome-shell-dark.css'
ORIGINAL_CSS = b'#lockDialogGroup { background-color: #123456; }\n'


class WallpaperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wallpaper-tests-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.destination = self.directory / 'output'
        self.destination.mkdir()
        self.image = self.directory / "wallpaper with spaces and 'quotes'.png"
        self.image.write_bytes(PNG)

    def test_copy_preserves_image_and_public_permissions(self):
        result = sync.copy_wallpaper(self.image.as_uri(), self.destination)
        self.assertEqual(result.read_bytes(), PNG)
        self.assertEqual(result.stat().st_mode & 0o777, 0o644)
        self.assertEqual([path.name for path in self.destination.iterdir()], ['current'])

    def test_missing_file_keeps_previous(self):
        target = self.destination / 'current'
        target.write_bytes(PNG)
        with self.assertRaises(OSError):
            sync.copy_wallpaper((self.directory / 'missing.png').as_uri(), self.destination)
        self.assertEqual(target.read_bytes(), PNG)

    def test_copy_does_not_force_disk_flushes(self):
        with patch.object(sync.os, 'fsync', side_effect=AssertionError('Unexpected disk flush')):
            result = sync.copy_wallpaper(self.image.as_uri(), self.destination)
        self.assertEqual(result.read_bytes(), PNG)

    def test_nonlocal_and_nonimage_sources_are_rejected(self):
        with self.assertRaises(ValueError):
            sync.copy_wallpaper('https://example.com/image.png', self.destination)
        text = self.directory / 'slides.xml'
        text.write_text('<background/>')
        with self.assertRaises(ValueError):
            sync.copy_wallpaper(text.as_uri(), self.destination)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_failed_copy_cleans_up_and_keeps_previous(self):
        target = self.destination / 'current'
        target.write_bytes(b'previous')
        with patch.object(sync.os, 'replace', side_effect=OSError('test failure')):
            with self.assertRaises(OSError):
                sync.copy_wallpaper(self.image.as_uri(), self.destination)
        self.assertEqual(target.read_bytes(), b'previous')
        self.assertEqual([path.name for path in self.destination.iterdir()], ['current'])

    def test_fifo_is_rejected_without_blocking(self):
        pipe = self.directory / 'pipe.png'
        os.mkfifo(pipe)
        with self.assertRaises(ValueError):
            sync.copy_wallpaper(pipe.as_uri(), self.destination)

    def test_watcher_catches_changes_without_touching_real_settings(self):
        other = self.directory / 'another.png'
        # Trailing data is legal for this copy test; it distinguishes the files.
        other.write_bytes(PNG + b'next-slide')
        code = '''
import importlib.util, os, signal, sys
from pathlib import Path
from gi.repository import Gio, GLib
spec = importlib.util.spec_from_file_location('sync', sys.argv[1])
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)
background = Gio.Settings.new('org.gnome.desktop.background')
interface = Gio.Settings.new('org.gnome.desktop.interface')
interface.set_string('color-scheme', 'prefer-dark')
for key in ('picture-uri', 'picture-uri-dark'):
    background.set_string(key, Path(sys.argv[2]).as_uri())
second = Path(sys.argv[3])
destination = Path(sys.argv[4])
def advance():
    for key in ('picture-uri', 'picture-uri-dark'):
        background.set_string(key, second.as_uri())
    return GLib.SOURCE_REMOVE
def finish():
    if (destination / 'current').read_bytes() != second.read_bytes():
        os._exit(2)
    os.kill(os.getpid(), signal.SIGTERM)
    return GLib.SOURCE_REMOVE
GLib.timeout_add(100, advance)
GLib.timeout_add(600, finish)
sys.argv = [sys.argv[0], '--directory', str(destination)]
raise SystemExit(sync.main())
'''
        env = dict(os.environ, GSETTINGS_BACKEND='memory')
        result = subprocess.run([
            sys.executable, '-I', '-c', code, str(DIRECTORY / 'sync-wallpaper.py'),
            str(self.image), str(other), str(self.destination)
        ], env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.destination / 'current').read_bytes(), other.read_bytes())


class ThemeTests(unittest.TestCase):
    def setUp(self):
        quiet = patch.object(theme, 'print', create=True)
        quiet.start()
        self.addCleanup(quiet.stop)
        self.temp = tempfile.TemporaryDirectory(prefix='theme-tests-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.resource = self.directory / 'active.gresource'
        self.state = self.directory / 'state'
        self.state.mkdir()
        self.wallpaper = self.state / 'wallpaper/current'
        self.wallpaper.parent.mkdir()
        self.wallpaper.write_bytes(PNG)
        for name, value in [('RESOURCE', self.resource), ('STATE', self.state), ('WALLPAPER', self.wallpaper)]:
            replacement = patch.object(theme, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.original = {
            CSS_NAME: ORIGINAL_CSS,
            '/org/gnome/shell/theme/background': PNG,
            '/org/gnome/shell/theme/unrelated.css': b'.example { color: red; }\n',
            '/another/preserved-binary': b'\x00\x01\xffbinary\x00',
        }
        theme.compile_entries(self.original, self.resource)

    def test_patch_preserves_unrelated_entries_and_source(self):
        before = self.resource.read_bytes()
        output = self.directory / 'patched.gresource'
        self.assertTrue(theme.build(self.resource, output, theme.DEFAULT_STYLE))
        result = theme.entries_in(output)
        self.assertEqual(self.resource.read_bytes(), before)
        for name, data in self.original.items():
            if name != CSS_NAME:
                self.assertEqual(result[name], data)
        self.assertIn(b'background-size: cover;', result[CSS_NAME])
        self.assertIn(self.wallpaper.as_uri().encode(), result[CSS_NAME])
        self.assertEqual(result[CSS_NAME].count(theme.BEGIN.encode()), 1)

    def test_patch_is_idempotent_and_removable(self):
        patched = self.directory / 'patched.gresource'
        theme.build(self.resource, patched, theme.DEFAULT_STYLE)
        unused = self.directory / 'unused.gresource'
        self.assertFalse(theme.build(patched, unused, theme.DEFAULT_STYLE))
        self.assertFalse(unused.exists())
        restored = self.directory / 'restored.gresource'
        theme.build(patched, restored, theme.DEFAULT_STYLE, remove=True)
        self.assertEqual(theme.entries_in(restored), self.original)

    def test_apply_and_restore_exact_original(self):
        before = self.resource.read_bytes()
        theme.apply(theme.DEFAULT_STYLE.copy())
        theme.restore()
        self.assertEqual(self.resource.read_bytes(), before)

    def test_style_change_keeps_original_rollback(self):
        before = self.resource.read_bytes()
        theme.apply(theme.DEFAULT_STYLE.copy())
        changed_style = dict(theme.DEFAULT_STYLE, **{'picture-options': 'scaled'})
        theme.apply(changed_style)
        theme.restore()
        self.assertEqual(self.resource.read_bytes(), before)

    def test_restore_keeps_newer_customizations(self):
        theme.apply(theme.DEFAULT_STYLE.copy())
        newer = theme.entries_in(self.resource)
        newer[CSS_NAME] += b'\n.customization { color: green; }\n'
        newer_resource = self.directory / 'newer.gresource'
        theme.compile_entries(newer, newer_resource)
        theme.atomic_copy(newer_resource, self.resource)
        theme.restore()
        result = theme.entries_in(self.resource)
        self.assertIn(b'.customization { color: green; }', result[CSS_NAME])
        self.assertNotIn(theme.BEGIN.encode(), result[CSS_NAME])

    def test_upgrade_rollback_restores_new_package_not_old_package(self):
        theme.apply(theme.DEFAULT_STYLE.copy())
        upgraded = dict(self.original, **{'/new-package-icon': b'new version'})
        new_resource = self.directory / 'package.gresource'
        theme.compile_entries(upgraded, new_resource)
        theme.atomic_copy(new_resource, self.resource)
        new_package_bytes = self.resource.read_bytes()
        theme.apply(None)
        theme.restore()
        self.assertEqual(self.resource.read_bytes(), new_package_bytes)

    def test_reject_css_injection_in_style(self):
        style = dict(theme.DEFAULT_STYLE, **{'primary-color': '#000000; malicious: true'})
        with self.assertRaises(ValueError):
            theme.wallpaper_css(style)


class UnitTests(unittest.TestCase):
    def test_runtime_argument_is_quoted_and_specifiers_are_literal(self):
        path = '/example/data with spaces/100%/$literal/"quote"/sync.py'
        rendered = units.render('ExecStart=/usr/bin/python -I @SCRIPT@\n', path)
        self.assertIn('100%%/$$literal/\\"quote\\"', rendered)
        self.assertNotIn('@SCRIPT@', rendered)
        self.assertIn('"/example/data with spaces/', rendered)

    def test_invalid_paths_or_templates_are_rejected(self):
        with self.assertRaises(ValueError):
            units.quote_argument('/example/bad\npath')
        with self.assertRaises(ValueError):
            units.render('No placeholder', '/example/script.py')


if __name__ == '__main__':
    unittest.main()
