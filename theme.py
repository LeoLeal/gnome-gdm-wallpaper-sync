#!/usr/bin/python -I
# gdm-wallpaper-sync managed helper
"""Patch only GDM's wallpaper CSS, preserving all other resource entries."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET


RESOURCE = Path('/usr/share/gnome-shell/gnome-shell-theme.gresource')
STATE = Path('/var/lib/gdm-wallpaper-sync')
WALLPAPER = STATE / 'wallpaper/current'
BEGIN = '/* BEGIN gdm-wallpaper-sync */'
END = '/* END gdm-wallpaper-sync */'
MARKER = re.compile(r'\n?' + re.escape(BEGIN) + r'.*?' + re.escape(END) + r'\n?', re.S)
DEFAULT_STYLE = {
    'picture-options': 'zoom',
    'color-shading-type': 'solid',
    'primary-color': '#000000',
    'secondary-color': '#000000',
}
SIZES = {
    'scaled': 'contain', 'zoom': 'cover', 'stretched': '100% 100%',
    'centered': 'auto', 'wallpaper': 'auto', 'spanned': 'cover',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validated_style(style):
    if set(style) != set(DEFAULT_STYLE):
        raise ValueError('Unexpected background style keys')
    if style['picture-options'] not in SIZES:
        raise ValueError('Select an image wallpaper before installing')
    if style['picture-options'] == 'spanned':
        raise ValueError('Spanned multi-monitor wallpapers are not supported')
    if style['color-shading-type'] not in ('solid', 'horizontal', 'vertical'):
        raise ValueError('Unsupported background shading')
    for key in ('primary-color', 'secondary-color'):
        if not isinstance(style[key], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', style[key]):
            raise ValueError('Background colors must use #RRGGBB notation')
    return style


def wallpaper_css(style):
    style = validated_style(style)
    repeat = 'repeat' if style['picture-options'] == 'wallpaper' else 'no-repeat'
    lines = [
        BEGIN,
        '.login-dialog { background: transparent; }',
        '#lockDialogGroup {',
        f'  background-image: url("{WALLPAPER.as_uri()}");',
        f'  background-color: {style["primary-color"]};',
        '  background-position: center;',
        f'  background-size: {SIZES[style["picture-options"]]};',
        f'  background-repeat: {repeat};',
    ]
    if style['color-shading-type'] != 'solid':
        lines.extend([
            f'  background-gradient-direction: {style["color-shading-type"]};',
            f'  background-gradient-start: {style["primary-color"]};',
            f'  background-gradient-end: {style["secondary-color"]};',
        ])
    lines.extend(['}', END, ''])
    return '\n' + '\n'.join(lines)


def entries_in(resource):
    listing = subprocess.check_output(['/usr/bin/gresource', 'list', str(resource)], text=True)
    return {name: subprocess.check_output([
        '/usr/bin/gresource', 'extract', str(resource), name
    ]) for name in listing.splitlines()}


def compile_entries(entries, output):
    with tempfile.TemporaryDirectory(prefix='gdm-wallpaper-build-', dir=output.parent) as temp:
        directory = Path(temp)
        root = ET.Element('gresources')
        resource = ET.SubElement(root, 'gresource', prefix='/')
        for index, (name, data) in enumerate(sorted(entries.items())):
            filename = f'{index}.data'
            (directory / filename).write_bytes(data)
            ET.SubElement(resource, 'file', alias=name.lstrip('/'), compressed='true').text = filename
        manifest = directory / 'resource.xml'
        ET.ElementTree(root).write(manifest, encoding='utf-8', xml_declaration=True)
        subprocess.run([
            '/usr/bin/glib-compile-resources', '--sourcedir', str(directory),
            '--target', str(output), str(manifest)
        ], check=True)
    # Verify every byte, including untouched icons and the embedded original image.
    if entries_in(output) != entries:
        raise ValueError('Resource verification failed; the active theme was not changed')


def build(source, output, style, remove=False):
    entries = entries_in(source)
    changed = 0
    for name, data in list(entries.items()):
        if not name.endswith('.css'):
            continue
        css = data.decode('utf-8')
        if not re.search(r'#lockDialogGroup\s*\{', css):
            continue
        clean = MARKER.sub('', css)
        updated = clean if remove else clean + wallpaper_css(style)
        if updated != css:
            entries[name] = updated.encode('utf-8')
            changed += 1
    if not changed:
        return False
    compile_entries(entries, output)
    return True


def atomic_copy(source, destination):
    descriptor, temporary = tempfile.mkstemp(prefix=f'.{destination.name}-', dir=destination.parent)
    try:
        with os.fdopen(descriptor, 'wb') as output, source.open('rb') as original:
            shutil.copyfileobj(original, output)
            os.fchmod(output.fileno(), 0o644)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_json(path, value):
    with tempfile.TemporaryDirectory(prefix='settings-', dir=STATE) as temp:
        source = Path(temp) / 'settings.json'
        source.write_text(json.dumps(value, indent=2) + '\n')
        atomic_copy(source, path)


def apply(style):
    if not WALLPAPER.is_file():
        raise ValueError('Seed the wallpaper using sync-wallpaper.py --once first')
    config = STATE / 'style.json'
    if style is None:
        style = json.loads(config.read_text()) if config.exists() else DEFAULT_STYLE.copy()
    style = validated_style(style)
    backups = STATE / 'backups'
    backups.mkdir(mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='theme-', dir=STATE) as temp:
        snapshot = Path(temp) / 'snapshot.gresource'
        atomic_copy(RESOURCE, snapshot)
        current_hash = digest(snapshot)
        output = Path(temp) / 'theme.gresource'
        if not build(snapshot, output, style):
            # A previously patched resource is already current.
            if not any(BEGIN.encode() in value for value in entries_in(snapshot).values()):
                raise ValueError('No supported GDM CSS found; refusing to modify the theme')
            write_json(config, style)
            print('The GDM wallpaper theme is already configured.')
            return

        # Reconfiguration must still undo the entire feature, not restore an
        # older version of our own patch. Reuse the clean baseline when possible.
        manifest = STATE / 'last-apply.json'
        previous = json.loads(manifest.read_text()) if manifest.exists() else None
        if previous and current_hash == previous['after']:
            baseline = backups / f'{previous["before"]}.gresource'
            if digest(baseline) != previous['before']:
                raise ValueError('The previous theme backup failed its checksum verification')
        else:
            baseline = Path(temp) / 'baseline.gresource'
            if not build(snapshot, baseline, style, remove=True):
                baseline = snapshot
        before = digest(baseline)
        backup = backups / f'{before}.gresource'
        if not backup.exists():
            atomic_copy(baseline, backup)
        if digest(RESOURCE) != current_hash:
            raise ValueError('Another program changed the theme during setup; retry the command')
        write_json(STATE / 'last-apply.json', {'before': before, 'after': digest(output)})
        write_json(config, style)
        atomic_copy(output, RESOURCE)
        print(f'Configured GDM wallpaper; original theme backed up to {backup}')


def restore():
    current_hash = digest(RESOURCE)
    manifest = STATE / 'last-apply.json'
    if manifest.exists():
        previous = json.loads(manifest.read_text())
        if digest(RESOURCE) == previous['after']:
            backup = STATE / 'backups' / f'{previous["before"]}.gresource'
            if digest(backup) != previous['before']:
                raise ValueError('The theme backup failed its checksum verification')
            if digest(RESOURCE) != current_hash:
                raise ValueError('Another program changed the theme during restore; retry the command')
            atomic_copy(backup, RESOURCE)
            print('Restored the theme from before the last sync patch.')
            return
    # Retain any newer GDM Settings/package changes instead of overwriting them.
    with tempfile.TemporaryDirectory(prefix='restore-', dir=STATE) as temp:
        snapshot = Path(temp) / 'snapshot.gresource'
        atomic_copy(RESOURCE, snapshot)
        output = Path(temp) / 'theme.gresource'
        if build(snapshot, output, DEFAULT_STYLE, remove=True):
            if digest(RESOURCE) != current_hash:
                raise ValueError('Another program changed the theme during restore; retry the command')
            atomic_copy(output, RESOURCE)
            print('Removed only the wallpaper-sync CSS; retained newer theme changes.')
        else:
            print('No wallpaper-sync CSS is present; nothing to restore.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    patch = commands.add_parser('apply')
    patch.add_argument('--style', help='Desktop background settings as JSON')
    commands.add_parser('restore')
    dry = commands.add_parser('build', help='Build a test resource without installing anything')
    dry.add_argument('--source', type=Path, required=True)
    dry.add_argument('--output', type=Path, required=True)
    dry.add_argument('--remove', action='store_true')
    args = parser.parse_args()
    if args.command == 'build':
        if args.source.resolve() == args.output.resolve():
            parser.error('The test output must not replace its source')
        if args.output.exists():
            parser.error('The test output already exists')
        changed = build(args.source, args.output, DEFAULT_STYLE, remove=args.remove)
        print('Built and verified the test resource.' if changed else 'No changes required.')
        return
    if os.geteuid() != 0:
        parser.error('apply/restore require sudo')
    if RESOURCE.is_symlink() or not RESOURCE.is_file():
        parser.error('The GNOME Shell resource must be a regular, non-symlink file')
    if not STATE.is_dir() or STATE.stat().st_uid != 0 or STATE.stat().st_mode & 0o022:
        parser.error('The state directory must be root-owned and not group/world writable')
    with (STATE / 'theme.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.command == 'apply':
            apply(json.loads(args.style) if args.style else None)
        else:
            restore()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'gdm-wallpaper-sync: {error}')
