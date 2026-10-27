# -*- coding: utf-8 -*-
"""Схемы алгоритмов по ГОСТ 19.701-90 (ЕСПД. Схемы алгоритмов, программ, данных и систем).

Символы (п. 3 ГОСТ): «Терминатор» (term), «Процесс» (proc), «Решение» (dec), «Данные» (io),
«Предопределённый процесс» (sub), «Подготовка» (prep), «Соединитель» (conn), «Комментарий» (note).
Размеры символов — a × b, где b = 2a (допускается ГОСТ), линии потока — горизонтальные и вертикальные,
стрелка ставится на конце линии.

Схема задаётся узлами на сетке (столбец, строка) и рёбрами:
    nodes = {"s": ("term", "Начало", 0, 0), ...}
    edges = [("s", "a"), ("d", "x", {"label": "да", "exit": "r", "enter": "t", "via": [(1.5, 3)]}), ...]
"""
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle, Circle

plt.rcParams["font.family"] = "Arial"

DPI = 200
COLW = 5.8     # шаг столбцов, см
ROWH = 2.0     # шаг строк, см
W, H = 4.5, 1.3   # символ: b × a, см
FS = 8.5


def _wrap(text, width):
    out = []
    for part in text.split("\n"):
        out.extend(textwrap.wrap(part, width, break_long_words=False) or [""])
    return "\n".join(out)


class _Node:
    def __init__(self, key, kind, text, col, row, w=None, h=None):
        self.key, self.kind, self.text = key, kind, text
        self.x, self.y = col * COLW, -row * ROWH
        self.w = w if w is not None else (0.7 if kind == "conn" else W * 1.15 if kind == "dec" else W)
        self.h = h if h is not None else (0.7 if kind == "conn" else 0.75 if kind == "term" else H)

    def anchor(self, side):
        x, y, w, h = self.x, self.y, self.w, self.h
        if self.kind == "io" and side in "lr":
            w = w - 0.35  # наклонные стороны параллелограмма
        return {"t": (x, y + h / 2), "b": (x, y - h / 2), "l": (x - w / 2, y), "r": (x + w / 2, y)}[side]


def _draw_node(ax, n):
    x, y, w, h = n.x, n.y, n.w, n.h
    kw = dict(fc="white", ec="black", lw=1.0, zorder=2)
    k = n.kind
    if k == "term":
        ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                    boxstyle=f"round,pad=0,rounding_size={h / 2}", **kw))
    elif k == "proc":
        ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, **kw))
    elif k == "sub":
        ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, **kw))
        for dx in (0.18, w - 0.18):
            ax.plot([x - w / 2 + dx] * 2, [y - h / 2, y + h / 2], color="black", lw=1.0, zorder=3)
    elif k == "dec":
        ax.add_patch(Polygon([(x, y + h / 2), (x + w / 2, y), (x, y - h / 2), (x - w / 2, y)], closed=True, **kw))
    elif k == "io":
        s = 0.35
        ax.add_patch(Polygon([(x - w / 2 + s, y + h / 2), (x + w / 2, y + h / 2), (x + w / 2 - s, y - h / 2),
                              (x - w / 2, y - h / 2)], closed=True, **kw))
    elif k == "prep":
        s = 0.35
        ax.add_patch(Polygon([(x - w / 2 + s, y + h / 2), (x + w / 2 - s, y + h / 2), (x + w / 2, y),
                              (x + w / 2 - s, y - h / 2), (x - w / 2 + s, y - h / 2), (x - w / 2, y)],
                             closed=True, **kw))
    elif k == "conn":
        ax.add_patch(Circle((x, y), w / 2, **kw))
    elif k == "note":
        ax.plot([x - w / 2 + 0.25, x - w / 2, x - w / 2, x - w / 2 + 0.25],
                [y + h / 2, y + h / 2, y - h / 2, y - h / 2], color="black", lw=1.0)
    ha = "left" if k == "note" else "center"
    tx = x - w / 2 + 0.12 if k == "note" else x
    ax.text(tx, y, _text(n), ha=ha, va="center", fontsize=FS if k != "dec" else FS - 0.5,
            zorder=4, linespacing=1.15)


def _text(n):
    if n.kind == "dec":
        width = int((n.w * 0.7) / 0.18)
    elif n.kind == "conn":
        width = 4
    else:
        width = int((n.w - 0.3) / 0.175)
    return _wrap(n.text, max(width, 6))


def _fit_height(n):
    """Символ растягивается по высоте, если текст не помещается в стандартный размер."""
    lines = _text(n).count("\n") + 1
    line_h = FS / 72 * 2.54 * 1.2
    need = lines * line_h * (1.6 if n.kind == "dec" else 1.0) + 0.3
    n.h = max(n.h, need)


def _orth(points, first):
    """Ломаная из вертикальных и горизонтальных отрезков: между соседними точками вставляется угол."""
    out = [points[0]]
    d = first
    for p in points[1:]:
        a = out[-1]
        if abs(a[0] - p[0]) > 1e-6 and abs(a[1] - p[1]) > 1e-6:
            out.append((a[0], p[1]) if d == "v" else (p[0], a[1]))
            d = "h" if d == "v" else "v"
        else:
            d = "v" if abs(a[0] - p[0]) <= 1e-6 else "h"
            d = "h" if d == "v" else "v"
        out.append(p)
    return out


def _route(a, b, exit_, enter, via):
    p0, p1 = a.anchor(exit_), b.anchor(enter)
    first = "v" if exit_ in "tb" else "h"
    if via:
        pts = [p0] + [(cx * COLW, -cy * ROWH) for cx, cy in via] + [p1]
        return _orth(pts, first)
    if exit_ == "b" and enter == "t":
        if abs(p0[0] - p1[0]) < 1e-6:
            return [p0, p1]
        my = p1[1] + 0.35 if p0[1] - p1[1] < ROWH + 0.1 else p0[1] - (ROWH - a.h) / 2
        return [p0, (p0[0], my), (p1[0], my), p1]
    if exit_ in "lr" and enter in "tb":
        return [p0, (p1[0], p0[1]), p1]
    if exit_ in "lr" and enter in "lr":
        if abs(p0[1] - p1[1]) < 1e-6:
            return [p0, p1]
        mx = (p0[0] + p1[0]) / 2
        return [p0, (mx, p0[1]), (mx, p1[1]), p1]
    if exit_ in "tb" and enter in "lr":
        return [p0, (p0[0], p1[1]), p1]
    return _orth([p0, p1], first)


def _label_at(ax, pts, exit_, text):
    (x0, y0), (x1, y1) = pts[0], pts[1]
    if exit_ == "b":
        ax.text(x0 + 0.12, y0 - 0.08, text, ha="left", va="top", fontsize=FS - 0.5, zorder=5)
    elif exit_ == "t":
        ax.text(x0 + 0.12, y0 + 0.08, text, ha="left", va="bottom", fontsize=FS - 0.5, zorder=5)
    elif exit_ == "r":
        ax.text(x0 + 0.1, y0 + 0.07, text, ha="left", va="bottom", fontsize=FS - 0.5, zorder=5)
    else:
        ax.text(x0 - 0.1, y0 + 0.07, text, ha="right", va="bottom", fontsize=FS - 0.5, zorder=5)


def draw(nodes, edges, out_png, title=None):
    ns = {}
    for key, spec in nodes.items():
        kind, text, col, row = spec[:4]
        extra = spec[4] if len(spec) > 4 else {}
        ns[key] = _Node(key, kind, text, col, row, extra.get("w"), extra.get("h"))
        if kind != "conn":
            _fit_height(ns[key])
    xs = [n.x - n.w / 2 for n in ns.values()] + [n.x + n.w / 2 for n in ns.values()]
    ys = [n.y - n.h / 2 for n in ns.values()] + [n.y + n.h / 2 for n in ns.values()]
    routes = []
    for e in edges:
        a, b = e[0], e[1]
        o = e[2] if len(e) > 2 else {}
        exit_ = o.get("exit", "b")
        enter = o.get("enter", "t")
        pts = _route(ns[a], ns[b], exit_, enter, o.get("via"))
        routes.append((pts, exit_, o))
        xs += [p[0] for p in pts]
        ys += [p[1] for p in pts]
    pad = 0.4
    x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad + 0.6, min(ys) - pad, max(ys) + pad
    fig = plt.figure(figsize=((x1 - x0) / 2.54, (y1 - y0) / 2.54))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")
    for n in ns.values():
        _draw_node(ax, n)
    for pts, exit_, o in routes:
        xs_, ys_ = zip(*pts)
        ax.plot(xs_[:-1] + (xs_[-1],), ys_, color="black", lw=1.0, zorder=1, solid_capstyle="butt")
        if o.get("arrow", True):
            ax.annotate("", xy=pts[-1], xytext=pts[-2],
                        arrowprops=dict(arrowstyle="-|>,head_length=0.45,head_width=0.18", color="black", lw=1.0,
                                        shrinkA=0, shrinkB=0), zorder=6)
        if o.get("label"):
            _label_at(ax, pts, exit_, o["label"])
    fig.savefig(out_png, dpi=DPI, facecolor="white")
    plt.close(fig)
    return out_png
