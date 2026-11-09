"""Monthly treasury summary as a PDF with simple charts.

The figures come from the admin's page, which already computes them; this
module validates them and draws them. No individual records or donor names.
"""

import io
import math
import re
from datetime import date
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

GREEN, RED = HexColor("#16a34a"), HexColor("#dc2626")
BLUE, ORANGE = HexColor("#2563eb"), HexColor("#f97316")
YELLOW, TRACK = HexColor("#facc15"), HexColor("#e5e7eb")
INK, MUTED = HexColor("#1d2433"), HexColor("#64748b")
MARGIN = 40
WIDTH = A4[0] - 2 * MARGIN
BAR_H = 11
MAX_ROWS = 200


def _num(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError("invalid number")
    return float(value)


def _text(value: Any, limit: int = 120) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid text")
    return value.strip()[:limit]


def _rows(value: Any) -> list:
    if not isinstance(value, list) or len(value) > MAX_ROWS:
        raise ValueError("invalid list")
    return value


def validate_report(data: dict) -> dict:
    """Return a clean copy of the report sent by the page; ValueError if malformed."""
    try:
        month = str(data["month"])
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            raise ValueError("invalid month")
        resumo, custos = data["resumo"], data["custos"]
        return {
            "month": month,
            "label": _text(data["label"], 40),
            "resumo": {
                k: _num(resumo[k])
                for k in ("lancamentos", "entradas", "saidas", "saldo", "validado")
            },
            "custos": {
                **{k: _num(custos[k]) for k in ("pagas", "contas", "pago")},
                "em_falta": [_text(c) for c in _rows(custos["em_falta"])],
            },
            "centros": [
                {"nome": _text(c["nome"]), "valor": _num(c["valor"])}
                for c in _rows(data["centros"])
            ],
            "resultados": [
                {
                    "nome": _text(r["nome"], 40),
                    **{k: _num(r[k]) for k in ("vendas", "custo", "tpa", "resultado")},
                }
                for r in _rows(data["resultados"])
            ],
        }
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("malformed report") from exc


def eur(value: float) -> str:
    text = f"{abs(value):,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"{'-' if round(value, 2) < 0 else ''}{text} €"


def signed(value: float) -> str:
    return f"{'+' if value >= 0 else ''}{eur(value)}"


class _Page:
    """Canvas with a top-down cursor that starts a new page when it runs out."""

    def __init__(self, buffer: io.BytesIO, title: str) -> None:
        self.c = canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
        self.c.setTitle(title)
        self.y = A4[1] - MARGIN

    def need(self, height: float) -> None:
        if self.y - height < MARGIN:
            self.c.showPage()
            self.y = A4[1] - MARGIN

    def text(
        self,
        x: float,
        text: str,
        size: float = 9,
        color: Any = INK,
        bold: bool = False,
        right: bool = False,
    ) -> None:
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        self.c.setFillColor(color)
        (self.c.drawRightString if right else self.c.drawString)(x, self.y, text)

    def bar(self, x: float, width: float, color: Any) -> None:
        if width > 0:
            self.c.setFillColor(color)
            self.c.rect(x, self.y - 2, width, BAR_H, stroke=0, fill=1)

    def section(self, title: str, height: float) -> None:
        self.need(height + 40)
        self.y -= 22
        self.text(MARGIN, title, 11, bold=True)
        self.y -= 18

    def note(self, text: str) -> None:
        for line in simpleSplit(text, "Helvetica", 9, WIDTH):
            self.need(14)
            self.text(MARGIN, line, 9, MUTED)
            self.y -= 13


def _resumo(p: _Page, r: dict) -> None:
    p.section("Resumo do mês", 70)
    rows = (
        ("Entradas", r["entradas"], GREEN, eur(r["entradas"])),
        ("Saídas", r["saidas"], RED, eur(r["saidas"])),
        ("Saldo", abs(r["saldo"]), GREEN if r["saldo"] >= 0 else RED, signed(r["saldo"])),
    )
    top = max(1.0, *(v for _, v, _, _ in rows))
    for label, value, color, shown in rows:
        p.text(MARGIN, label)
        p.bar(MARGIN + 70, value / top * (WIDTH - 170), color)
        p.text(MARGIN + WIDTH, shown, bold=True, right=True)
        p.y -= 17
    validado = f"{r['validado']:.1f}".replace(".", ",")
    p.note(f"{int(r['lancamentos'])} lançamentos · {validado}% validados")


def _custos(p: _Page, c: dict) -> None:
    p.section("Custos fixos do mês", 50)
    share = c["pagas"] / c["contas"] if c["contas"] else 0
    p.bar(MARGIN, WIDTH - 90, TRACK)
    p.bar(MARGIN, share * (WIDTH - 90), GREEN)
    p.text(MARGIN + WIDTH, f"{int(c['pagas'])} de {int(c['contas'])} pagas", bold=True, right=True)
    p.y -= 17
    p.note(f"Pago {eur(c['pago'])}")
    if c["em_falta"]:
        p.note("Em falta: " + ", ".join(c["em_falta"]))


def _centros(p: _Page, centros: list[dict]) -> None:
    p.section("Centros de custo", 40)
    if not centros:
        p.note("Sem movimentos no mês.")
        return
    label_w, value_w = 190, 75
    half = (WIDTH - label_w - value_w) / 2
    axis = MARGIN + label_w + half
    top = max(1.0, *(abs(c["valor"]) for c in centros))
    for c in sorted(centros, key=lambda x: -x["valor"]):
        p.need(16)
        p.text(MARGIN, c["nome"][:38], 8.5)
        size = abs(c["valor"]) / top * half
        if c["valor"] >= 0:
            p.bar(axis, size, GREEN)
        else:
            p.bar(axis - size, size, RED)
        p.c.setStrokeColor(MUTED)
        p.c.line(axis, p.y - 4, axis, p.y + BAR_H)
        p.text(MARGIN + WIDTH, signed(c["valor"]), 8.5, right=True)
        p.y -= 15


def _resultados(p: _Page, resultados: list[dict]) -> None:
    p.section("Livraria e Verbo Café", 48 * len(resultados))

    def parts(r: dict) -> tuple:
        result = GREEN if r["resultado"] >= 0 else RED
        return (
            ("Recebido", r["vendas"], BLUE, eur(r["vendas"])),
            ("Aluguer e comissões TPA", r["tpa"], ORANGE, eur(r["tpa"])),
            ("Pagamentos", r["custo"], YELLOW, eur(r["custo"])),
            ("Resultado", r["resultado"], result, signed(r["resultado"])),
        )

    # Same scale for both lines; every segment is its own amount, not a share of the sales.
    top = max(1.0, *(sum(abs(v) for _, v, _, _ in parts(r)) for r in resultados))
    scale = (WIDTH - 80) / top
    column = (WIDTH - 80) / 4
    for r in resultados:
        p.need(48)
        p.text(MARGIN, r["nome"], bold=True)
        x = MARGIN + 80
        for _, value, color, _ in parts(r):
            p.bar(x, abs(value) * scale, color)
            x += abs(value) * scale
        p.y -= 17
        for i, (label, _, color, _) in enumerate(parts(r)):
            p.bar(MARGIN + 80 + i * column, 8, color)
            p.text(MARGIN + 92 + i * column, label, 8, MUTED)
        p.y -= 12
        for i, (_, _, _, shown) in enumerate(parts(r)):
            p.text(MARGIN + 92 + i * column, shown, 9, bold=True)
        p.y -= 24


def build_pdf(report: dict) -> bytes:
    title = f"Resumo Tesouraria · {report['label']}"
    buffer = io.BytesIO()
    p = _Page(buffer, title)
    p.y -= 8
    p.text(MARGIN, title, 16, bold=True)
    p.y -= 16
    p.text(MARGIN, f"Gerado em {date.today():%d/%m/%Y}", 9, MUTED)
    _resumo(p, report["resumo"])
    _custos(p, report["custos"])
    _centros(p, report["centros"])
    if report["resultados"]:
        _resultados(p, report["resultados"])
    p.c.save()
    return buffer.getvalue()
