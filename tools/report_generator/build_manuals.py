# -*- coding: utf-8 -*-
"""Сборка эксплуатационных документов базовой редакции: python build_manuals.py [user|ops]

Нужны Windows + MS Word, Java 11+ (plantuml.jar рядом). Снимки экранов делает screens_basic.py интерпретатором
из переменной SCREENS_PYTHON (в нём должны быть Flask и playwright), по умолчанию — текущим.
Результат: docs/Руководство_пользователя.docx/.pdf, docs/Руководство_по_эксплуатации.docx/.pdf,
схемы и снимки — в diagrams/manuals."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import time

import win32com.client

import flows_basic
import manual_basic as M
import manualgen
import uml_basic

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT_DOCS = os.path.join(ROOT, "docs")
OUT_FIGS = os.path.join(ROOT, "diagrams", "manuals")


def demo_counts(py):
    """Число строк в таблицах демо-базы (demo.py во временной копии программы)."""
    import shutil
    work = os.path.join(tempfile.mkdtemp(prefix="creditdss-basic-demo-"), "app")
    shutil.copytree(os.path.join(ROOT, "app"), work, ignore=shutil.ignore_patterns(
        ".venv", "wheels", "__pycache__", "creditdss.db", "secret.key"))
    subprocess.run([py, "demo.py"], cwd=work, check=True, stdout=subprocess.DEVNULL)
    c = sqlite3.connect(os.path.join(work, "creditdss.db"))
    out = {t: c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
           for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    c.close()
    return out


def main(args):
    which = [a for a in args if a in ("user", "ops")] or ["user", "ops"]
    py = os.environ.get("SCREENS_PYTHON", sys.executable)
    os.makedirs(OUT_FIGS, exist_ok=True)
    t0 = time.time()
    figs = flows_basic.make_all(OUT_FIGS)
    figs.update(uml_basic.make_all(OUT_FIGS))
    schema = figs.pop("schema")
    shots_dir = os.path.join(OUT_FIGS, "screens")
    subprocess.run([py, os.path.join(HERE, "screens_basic.py"), shots_dir], check=True,
                   env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    shots = {f[4:-4]: os.path.join(shots_dir, f) for f in os.listdir(shots_dir) if f.startswith("scr_")}
    counts = demo_counts(py)
    print(f"схемы и снимки: {time.time() - t0:.0f} с", flush=True)

    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        if "user" in which:
            t = time.time()
            out = os.path.join(OUT_DOCS, "Руководство_пользователя.docx")
            _, pages = manualgen.build_final(M.user_guide(figs, shots), out, M.INFO_USER, M.ANN_USER, word=word)
            print(f"руководство пользователя: {pages} стр., {time.time() - t:.0f} с", flush=True)
        if "ops" in which:
            t = time.time()
            out = os.path.join(OUT_DOCS, "Руководство_по_эксплуатации.docx")
            _, pages = manualgen.build_final(M.ops_guide(figs, schema, counts), out, M.INFO_OPS, M.ANN_OPS, word=word)
            print(f"руководство по эксплуатации: {pages} стр., {time.time() - t:.0f} с", flush=True)
    finally:
        word.Quit()


if __name__ == "__main__":
    os.makedirs(OUT_DOCS, exist_ok=True)
    main(sys.argv[1:])
