# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe for CalendarReminder tray app.

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['calendar_reminder/tray.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.yaml', '.'),
    ],
    hiddenimports=collect_submodules('pystray') + collect_submodules('PIL'),
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='CalendarReminder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
