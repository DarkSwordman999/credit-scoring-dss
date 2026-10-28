# -*- coding: utf-8 -*-
"""ER-диаграммы и словарь данных по реальной базе SQLite (PRAGMA table_info / foreign_key_list).

Схема читается из файла БД, созданного программой (миграциями или schema.sql), поэтому диаграмма
всегда совпадает с тем, что лежит в базе."""
import sqlite3
from contextlib import closing


def introspect(db_path):
    """{таблица: {"cols": [(имя, тип, not null, pk)], "fks": [(столбец, таблица, столбец)]}}"""
    out = {}
    with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as c:
        names = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "AND name <> 'alembic_version' ORDER BY name")]
        for t in names:
            cols = [(r[1], (r[2] or "").upper(), bool(r[3]) or bool(r[5]), bool(r[5]))
                    for r in c.execute(f"PRAGMA table_info('{t}')")]
            fks = [(r[3], r[2], r[4] or "id") for r in c.execute(f"PRAGMA foreign_key_list('{t}')")]
            uniq = set()
            for idx in c.execute(f"PRAGMA index_list('{t}')"):
                if idx[2]:
                    cs = [r[2] for r in c.execute(f"PRAGMA index_info('{idx[1]}')")]
                    if len(cs) == 1:
                        uniq.add(cs[0])
            out[t] = {"cols": cols, "fks": fks, "unique": uniq}
    return out


def _type(t):
    return (t.replace("DATETIME", "TIMESTAMP").replace("VARCHAR", "VARCHAR")
            .replace("NUMERIC(14, 2)", "NUMERIC(14,2)"))


def puml(schema, tables, ref_tables=(), names=None, compact=False, direction="top to bottom"):
    """Текст PlantUML (без @startuml): tables — детально, ref_tables — только первичный ключ.
    names — {таблица: русское название}; compact — только имена сущностей (обзорная схема)."""
    names = names or {}
    lines = [f"{direction} direction", "hide circle", "skinparam linetype ortho",
             "skinparam entity {", "  BackgroundColor white", "}"]
    shown = list(tables) + [t for t in ref_tables if t not in tables]
    for t in shown:
        title = f"{t}" + (f"\\n({names[t]})" if t in names else "")
        lines.append(f'entity "{title}" as {t} {{')
        if not compact:
            info = schema[t]
            fk_cols = {f[0] for f in info["fks"]}
            pk = [c for c in info["cols"] if c[3]]
            for c in pk:
                lines.append(f"  * {c[0]} : {_type(c[1])} <<PK>>")
            if t in tables:
                lines.append("  --")
                for name, typ, nn, is_pk in info["cols"]:
                    if is_pk:
                        continue
                    mark = "* " if nn else "  "
                    tags = []
                    if name in fk_cols:
                        tags.append("FK")
                    if name in info["unique"]:
                        tags.append("U")
                    tag = (" <<" + ",".join(tags) + ">>") if tags else ""
                    lines.append(f"  {mark}{name} : {_type(typ)}{tag}")
        lines.append("}")
    shown_set = set(shown)
    for t in shown:
        for col, ref, refcol in schema[t]["fks"]:
            if ref not in shown_set or (t not in tables and ref not in tables):
                continue
            nn = next(c[2] for c in schema[t]["cols"] if c[0] == col)
            many_fk = sum(1 for f in schema[t]["fks"] if f[1] == ref) > 1
            label = f" : {col}" if many_fk or compact is False and col != f"{ref.rstrip('s')}_id" else ""
            left = "||" if nn else "|o"
            lines.append(f"{ref} {left}--o{{ {t}{label}")
    return "\n".join(lines)


def dictionary_rows(schema, table, descr):
    """Строки таблицы словаря данных: поле, тип, ключ/ограничения, описание."""
    rows = []
    info = schema[table]
    fks = {f[0]: f for f in info["fks"]}
    for name, typ, nn, pk in info["cols"]:
        keys = []
        if pk:
            keys.append("PK")
        if name in fks:
            keys.append(f"FK → {fks[name][1]}")
        if name in info["unique"]:
            keys.append("уникальное")
        if nn and not pk:
            keys.append("NOT NULL")
        rows.append([name, _type(typ), ", ".join(keys), descr.get((table, name)) or descr.get(name, "")])
    return rows
