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
AMBER, TRACK = HexColor("#f59e0b"), HexColor("#e5e7eb")
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
                **{k: _num(custos[k]) for k in ("pagas", "contas", "pago", "estimado")},
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
        p.note(
            f"Em falta {eur(c['estimado'])} (estimativa pelo mês anterior): "
            + ", ".join(c["em_falta"])
        )


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
    p.section("Livraria e Verbo Café", 30 + 34 * len(resultados))
    x = MARGIN
    for label, color in (("Custo", RED), ("TPA", AMBER), ("Resultado", GREEN)):
        p.bar(x, 10, color)
        p.text(x + 14, label, 8.5, MUTED)
        x += 80
    p.y -= 18
    top = max(1.0, *(max(r["vendas"], r["custo"] + r["tpa"]) for r in resultados))
    scale = (WIDTH - 80) / top
    for r in resultados:
        p.text(MARGIN, r["nome"])
        x = MARGIN + 80
        for value, color in (
            (r["custo"], RED),
            (r["tpa"], AMBER),
            (max(r["resultado"], 0), GREEN),
        ):
            p.bar(x, value * scale, color)
            x += value * scale
        p.y -= 14
        p.text(MARGIN + 80, f"Recebido {eur(r['vendas'])}", 8.5, MUTED)
        color = GREEN if r["resultado"] >= 0 else RED
        p.text(MARGIN + WIDTH, f"Resultado {signed(r['resultado'])}", 9, color, True, True)
        p.y -= 20


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
