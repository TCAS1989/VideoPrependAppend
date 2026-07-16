# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the WGU Video Brander.

Builds a one-folder app (fast startup) containing:
  * gui.py entry point
  * bundled ffmpeg.exe / ffprobe.exe        -> _internal/ffmpeg/
  * bundled default branding images         -> _internal/assets/
  * tkinterdnd2 drag-and-drop library data

Build with:   python -m PyInstaller WGUVideoBrander.spec --noconfirm
Output:       dist/WGUVideoBrander/WGUVideoBrander.exe
"""

from PyInstaller.utils.hooks import collect_data_files

datas = [
    ("ffmpeg/ffmpeg.exe", "ffmpeg"),
    ("ffmpeg/ffprobe.exe", "ffmpeg"),
    ("assets/intro_template.png", "assets"),   # WGU title slide (intro)
    ("assets/AppendAsset.png", "assets"),      # WGU end slide (outro)
]
# tkinterdnd2 ships the tkdnd tcl library it needs at runtime.
datas += collect_data_files("tkinterdnd2")

block_cipher = None

a = Analysis(
    ["gui.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["tkinterdnd2"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WGUVideoBrander",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,       # windowed app, no console
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="WGUVideoBrander",
)
