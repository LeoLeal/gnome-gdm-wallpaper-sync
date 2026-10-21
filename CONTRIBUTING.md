# Contributing

Install the system test dependencies listed in the README; PyGObject and GSettings
schemas are distro dependencies, not bundled Python packages.

```bash
python -B -m unittest -v test_sync.py
bash -n install.sh uninstall.sh
```

Use synthetic images/resources and temporary directories in automated tests.
Tests must not patch system files, install units, restart GDM, modify real
wallpaper preferences or depend on the checkout's absolute location. Set
`TMPDIR` if a non-default temporary location is required.

For changes to theme patching, test idempotence, rollback, resource preservation
and concurrent-change detection. Manual GDM tests should be performed only after
saving work and having a recovery path. Include GNOME/GDM versions and distro
details in reports; redact personal wallpaper paths, usernames and journals.

Keep platform assumptions documented in PORTABILITY.md. Contributions use the
project's MIT license. This project does not bundle GNOME theme assets.
