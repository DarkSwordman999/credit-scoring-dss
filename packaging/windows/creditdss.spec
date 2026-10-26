# -*- mode: python ; coding: utf-8 -*-
# Сборка: pyinstaller packaging/windows/creditdss.spec (из каталога backend, после npm run build)
import os
from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", "..", "backend"))
PKG = os.path.join(ROOT, "creditdss")

datas = [
    (os.path.join(PKG, "static"), "creditdss/static"),
    (os.path.join(PKG, "migrations"), "creditdss/migrations"),
    (os.path.join(PKG, "fonts"), "creditdss/fonts"),
]
hidden = (collect_submodules("creditdss") + collect_submodules("uvicorn") + collect_submodules("apscheduler")
          + collect_submodules("ldap3") + ["openpyxl", "psycopg", "multipart", "fpdf"])

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "playwright", "numpy", "pandas"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="КредитныйСкоринг",
    console=True,
    icon=os.path.join(SPECPATH, "creditdss.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="CreditDSS")
