"""Выгрузка отчётов в PDF (С-16): альбомный A4, шрифт DejaVu Sans с кириллицей."""
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

from fastapi.responses import Response
from fpdf import FPDF
from fpdf.fonts import FontFace

FONTS = Path(__file__).resolve().parent.parent / "fonts"
MAX_ROWS = 3000       # строк одной таблицы в PDF; полностью — в выгрузке XLSX
LONG_TABLE = 150      # с этого числа строк таблица выводится построчно, без переноса текста


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "да" if v else "нет"
    if isinstance(v, float):
        return f"{v:,.2f}".replace(",", " ").replace(".", ",")
    if isinstance(v, int):
        return f"{v:,}".replace(",", " ")
    if isinstance(v, datetime):
        return v.strftime("%d.%m.%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d.%m.%Y")
    return str(v)


def build(title: str, meta: list[tuple[str, str]], tables: list[dict]) -> bytes:
    """tables: [{"title": str, "headers": [...], "rows": [[...]]}]"""
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_font("DejaVu", "", str(FONTS / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(FONTS / "DejaVuSans-Bold.ttf"))
    pdf.set_auto_page_break(True, margin=12)
    pdf.add_page()
    pdf.set_font("DejaVu", "B", 14)
    pdf.multi_cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 9)
    for k, v in meta:
        pdf.cell(0, 5, f"{k}: {v}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"Сформирован: {datetime.now():%d.%m.%Y %H:%M}", new_x="LMARGIN", new_y="NEXT")
    for t in tables:
        pdf.ln(3)
        pdf.set_font("DejaVu", "B", 11)
        pdf.cell(0, 7, t["title"], new_x="LMARGIN", new_y="NEXT")
        if not t["rows"]:
            pdf.set_font("DejaVu", "", 9)
            pdf.cell(0, 5, "Нет данных за период", new_x="LMARGIN", new_y="NEXT")
            continue
        pdf.set_font("DejaVu", "", 8)
        widths = _widths(t["headers"], t["rows"])
        rows = t["rows"][:MAX_ROWS]
        if len(rows) > LONG_TABLE:
            _fast_table(pdf, t["headers"], rows, widths)
        else:
            with pdf.table(col_widths=widths, headings_style=FontFace(emphasis="BOLD", fill_color=(227, 234, 244)),
                           line_height=4.5, text_align="LEFT") as table:
                table.row([str(h) for h in t["headers"]])
                for r in rows:
                    table.row([_fmt(v) for v in r])
        if len(t["rows"]) > MAX_ROWS:
            pdf.set_font("DejaVu", "", 8)
            pdf.cell(0, 5, f"Показаны первые {MAX_ROWS} строк из {len(t['rows'])}; полностью таблица есть "
                           f"в выгрузке XLSX", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _fit(pdf: FPDF, text: str, width: float) -> str:
    """Текст, обрезанный многоточием по ширине колонки."""
    if pdf.get_string_width(text) <= width:
        return text
    while text and pdf.get_string_width(text + "…") > width:
        text = text[:-1]
    return text + "…"


def _fast_table(pdf: FPDF, headers: list, rows: list, widths: tuple) -> None:
    """Длинная таблица построчно, без переноса текста в ячейках: табличный вывод fpdf2 раскладывает каждую
    ячейку и на тысячах строк работает десятки секунд. Шапка повторяется на каждой странице."""
    scale = pdf.epw / sum(widths)
    cols = [w * scale for w in widths]
    h = 4.5

    def head():
        pdf.set_font("DejaVu", "B", 8)
        pdf.set_fill_color(227, 234, 244)
        for w, title in zip(cols, headers):
            pdf.cell(w, h + 1, _fit(pdf, str(title), w - 1), border=1, fill=True)
        pdf.ln()
        pdf.set_font("DejaVu", "", 8)

    head()
    for r in rows:
        if pdf.will_page_break(h):
            pdf.add_page()
            head()
        for w, v in zip(cols, r):
            pdf.cell(w, h, _fit(pdf, _fmt(v), w - 1), border=1)
        pdf.ln()


def _widths(headers, rows) -> tuple:
    lens = []
    for i, h in enumerate(headers):
        cells = [len(_fmt(r[i])) for r in rows[:200] if i < len(r)]
        lens.append(max(6, min(40, max([len(str(h)) * 0.8] + cells))))
    return tuple(lens)


def response(data: bytes, filename: str) -> Response:
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})
