# PyInstaller spec — onedir build (fast startup, no self-extraction).
# Build with:  pyinstaller --noconfirm mp3csvtagger.spec
# Output:      dist/MP3CsvTagger/MP3CsvTagger.exe (plus support files)
import os

block_cipher = None

a = Analysis(
    ["run_gui.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=["mutagen"],
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
    [],
    exclude_binaries=True,
    name="MP3CsvTagger",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI program; use the CLI from a pip install for a console
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="MP3CsvTagger",
)
