# master_control.spec
# Build from project root with:
#   pyinstaller master_control.spec --clean

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
    [],
    exclude_binaries=True,
    name="AutomationMachine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / "icon.png"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="master_control",
)