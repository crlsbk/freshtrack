# -*- mode: python ; coding: utf-8 -*-
# PyInstaller (onedir). Desde la raíz del repo:
#   .venv/bin/pyinstaller desktop/freshtrack_desktop.spec --noconfirm --distpath desktop/dist --workpath desktop/build
from pathlib import Path

REPO = Path(SPECPATH).resolve().parent  # SPECPATH = desktop/
DESKTOP = REPO / "desktop"

a = Analysis(
    [str(DESKTOP / "run_desktop.py")],
    pathex=[str(DESKTOP)],
    binaries=[],
    # Los XSD viajan en <bundle>/contracts/xsd (lo que busca core/config.py::xsd_dir)
    datas=[(str(REPO / "contracts" / "xsd"), "contracts/xsd")],
    hiddenimports=["freshtrack_desktop.ui.pages"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "app"],  # la app nunca importa el backend (app/)
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FreshTrackDesktop",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="FreshTrackDesktop")
