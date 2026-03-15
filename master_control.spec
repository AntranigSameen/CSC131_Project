# master_control.spec
# Build from project root:
#   pyinstaller master_control.spec

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

project_root = Path.cwd()

hiddenimports = []
hiddenimports += collect_submodules("Proper_MS")
hiddenimports += collect_submodules("RQI_EmailSheets")

datas = [
    (str(project_root / ".env"), "."),
    (str(project_root / "service_account.json"), "."),
    (str(project_root / "google_sheet_api_key.json"), "."),
    (str(project_root / "icon.png"), "."),
]

a = Analysis(
    ["Proper_MS/master_control.py"],
    pathex=[str(project_root), str(project_root / "Proper_MS")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="master_control",
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
    entitlements_file=None,
    icon=str(project_root / "icon.png"),
)