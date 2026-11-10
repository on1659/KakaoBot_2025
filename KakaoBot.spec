# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_all


datas = [
    ("config/DefaultSetting.template.ini", "config"),
    ("config/api_key.json.example", "config"),
    ("Lib/web/index.html", "Lib/web"),
]
binaries = []
hiddenimports = []

# pillow-heif registers a Pillow plugin at runtime and ships native binaries.
try:
    heif_datas, heif_binaries, heif_hiddenimports = collect_all("pillow_heif")
    datas += heif_datas
    binaries += heif_binaries
    hiddenimports += heif_hiddenimports
except Exception:
    # The build will still surface a clear missing-module warning when the
    # optional HEIF dependency is absent from the build environment.
    pass


a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["flask", "pytest"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KakaoBot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=os.environ.get("KAKAOBOT_CONSOLE", "0") == "1",
    disable_windowed_traceback=False,
    argv_emulation=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="KakaoBot",
)

