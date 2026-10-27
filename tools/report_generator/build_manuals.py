# -*- coding: utf-8 -*-
"""Сборка эксплуатационных документов полной редакции: python build_manuals.py [папка демо-данных] [user|ops]

Нужны Windows + MS Word, Java 11+ (plantuml.jar рядом), backend/.venv с playwright.
Без папки демо-данных она создаётся во временной папке командой «creditdss demo» (около двух минут).
Результат: docs/Руководство_пользователя.docx/.pdf, docs/Руководство_по_эксплуатации.docx/.pdf,
схемы и снимки экранов — в diagrams/manuals."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import time

import win32com.client

import flows_credit
import manual_credit as M
import manualgen
import uml_credit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BACKEND = os.path.join(ROOT, "backend")
VENV_PY = os.path.join(BACKEND, ".venv", "Scripts", "python.exe")
OUT_DOCS = os.path.join(ROOT, "docs")
OUT_FIGS = os.path.join(ROOT, "diagrams", "manuals")


def demo_data():
    d = tempfile.mkdtemp(prefix="creditdss-demo-")
    env = dict(os.environ, CREDITDSS_DATA_DIR=d, CREDITDSS_SCHEDULER_ENABLED="false", PYTHONIOENCODING="utf-8")
    subprocess.run([VENV_PY, "-m", "creditdss.cli", "demo"], cwd=BACKEND, env=env, check=True)
    return d


def counts(db):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out = {t: c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
           for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    c.close()
    return out


def main(args):
    which = [a for a in args if a in ("user", "ops")] or ["user", "ops"]
    rest = [a for a in args if a not in ("user", "ops")]
    data = rest[0] if rest else demo_data()
    db = os.path.join(data, "creditdss.db")
    os.makedirs(OUT_FIGS, exist_ok=True)
    t0 = time.time()
    figs = {f"alg_{k}": v for k, v in flows_credit.make_all(OUT_FIGS).items()}
    figs.update(uml_credit.make_all(db, OUT_FIGS))
    schema = figs.pop("schema")
    shots_dir = os.path.join(OUT_FIGS, "screens")
    subprocess.run([VENV_PY, os.path.join(HERE, "screens_credit.py"), data, shots_dir], check=True,
                   env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    shots = {f[4:-4]: os.path.join(shots_dir, f) for f in os.listdir(shots_dir) if f.startswith("scr_")}
    figs.update({f"scr_{k}": v for k, v in shots.items()})
    print(f"схемы и снимки: {time.time() - t0:.0f} с", flush=True)

    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        if "user" in which:
            t = time.time()
            out = os.path.join(OUT_DOCS, "Руководство_пользователя.docx")
            splits, pages = manualgen.build_final(M.user_guide(figs, shots), out, M.INFO_USER, M.ANN_USER, word=word)
            print(f"руководство пользователя: {pages} стр., {time.time() - t:.0f} с", flush=True)
        if "ops" in which:
            t = time.time()
            out = os.path.join(OUT_DOCS, "Руководство_по_эксплуатации.docx")
            splits, pages = manualgen.build_final(M.ops_guide(figs, schema, counts(db)), out, M.INFO_OPS, M.ANN_OPS,
                                                  word=word)
            print(f"руководство по эксплуатации: {pages} стр., {time.time() - t:.0f} с", flush=True)
    finally:
        word.Quit()


if __name__ == "__main__":
    main(sys.argv[1:])
