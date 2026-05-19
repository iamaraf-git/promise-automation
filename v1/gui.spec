# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# ----------------------------
# PATH CONFIGURATIONS
# ----------------------------
# CHANGE 'YOUR_WINDOWS_USERNAME' to match your local computer's profile folder name
playwright_path = r'C:\Users\YOUR_WINDOWS_USERNAME\AppData\Local\ms-playwright'

added_files = [
    ('azbilling-new-logo.ico', '.')
]

# Automatically sweep and bundle the Playwright browser system path if it exists
if os.path.exists(playwright_path):
    added_files.append((playwright_path, 'playwright'))

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=['playwright.sync_api'],
    hookspath=[],
    hooksconfig={},
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
    name='Promise_Eligibility_Checker_v1',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements=None,
    icon='azbilling-new-logo.ico'
)
