# PyInstaller spec for MolView macOS .app bundle
# Build with: pyinstaller MolView.spec
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Bundle Ketcher/JSME web assets and the app icon as data files alongside
# molview/ so that Path(__file__).parent lookups continue to work.
datas = [
    ('src/molview/gui/structure_editor/ketcher', 'molview/gui/structure_editor/ketcher'),
    ('src/molview/gui/structure_editor/jsme',    'molview/gui/structure_editor/jsme'),
    ('src/molview/gui/molview_icon.png',         'molview/gui'),
    ('src/molview/gui/molview_icon.icns',        'molview/gui'),
]

# RDKit ships C extensions and data files that PyInstaller needs help finding.
datas += collect_data_files('rdkit')
hiddenimports = collect_submodules('rdkit') + [
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebChannel',
]

a = Analysis(
    ['src/molview/__main__.py'],
    pathex=['src'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='MolView',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,             # ← no terminal window
    disable_windowed_traceback=False,
    argv_emulation=True,       # macOS: forward Finder file-open events
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='src/molview/gui/molview_icon.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='MolView',
)

app = BUNDLE(
    coll,
    name='MolView.app',
    icon='src/molview/gui/molview_icon.icns',
    bundle_identifier='com.molview.MolView',
    info_plist={
        'CFBundleName': 'MolView',
        'CFBundleDisplayName': 'MolView',
        'CFBundleShortVersionString': '0.1.0',
        'CFBundleVersion': '0.1.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '11.0',
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeName': 'Chemical Data',
                'CFBundleTypeRole': 'Editor',
                'LSItemContentTypes': ['public.comma-separated-values-text'],
                'CFBundleTypeExtensions': ['csv', 'xlsx', 'xls', 'sdf', 'mol'],
            }
        ],
    },
)
