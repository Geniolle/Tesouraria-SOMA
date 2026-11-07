import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard"))

from report_mail import active_emails, build_message  # noqa: E402
from report_pdf import build_pdf, eur, signed, validate_report  # noqa: E402


def report(**changes: object) -> dict:
    return {
        "month": "2026-10",
        "label": "Outubro 2026",
        "resumo": {
            "lancamentos": 312,
            "entradas": 18450,
            "saidas": 15230.5,
            "saldo": 3219.5,
            "validado": 98.1,
        },
        "custos": {
            "pagas": 9,
            "contas": 12,
            "pago": 5100,
            "estimado": 1700,
            "em_falta": ["ÁGUA", "LUZ"],
        },
        "centros": [{"nome": "Dízimos", "valor": 14200}, {"nome": "Missões", "valor": -1710}],
        "resultados": [
            {"nome": "Livraria", "vendas": 1240, "custo": 780, "tpa": 150, "resultado": 310},
            {"nome": "Verbo Café", "vendas": 100, "custo": 180, "tpa": 20, "resultado": -100},
        ],
        **changes,
    }


def test_money_format() -> None:
    assert eur(1234.5) == "1.234,50 €"
    assert eur(-0.001) == "0,00 €"
    assert signed(-1710) == "-1.710,00 €"
    assert signed(310) == "+310,00 €"


@pytest.mark.parametrize(
    "bad",
    [
        {"month": "2026-13"},
        {"month": "../x"},
        {"label": ""},
        {"resumo": {"entradas": 1}},
        {"centros": [{"nome": "x", "valor": float("nan")}]},
        {"centros": [{"nome": "x", "valor": True}]},
        {"centros": [{"nome": "x", "valor": 1}] * 201},
        {"resultados": "x"},
    ],
)
def test_validate_rejects_bad_reports(bad: dict) -> None:
    with pytest.raises(ValueError):
        validate_report(report(**bad))


def test_pdf_handles_many_centres_and_empty_month() -> None:
    many = [{"nome": f"Centro {i}", "valor": i - 50} for i in range(100)]
    pdf = build_pdf(validate_report(report(centros=many)))
    assert pdf.startswith(b"%PDF")
    assert b"/Count 3" in pdf or b"/Count 4" in pdf
    zeros = dict.fromkeys(("lancamentos", "entradas", "saidas", "saldo", "validado"), 0)
    empty = report(
        resumo=zeros,
        custos={"pagas": 0, "contas": 0, "pago": 0, "estimado": 0, "em_falta": []},
        centros=[],
    )
    assert build_pdf(validate_report(empty)).startswith(b"%PDF")


def test_only_active_accounts_receive_the_email() -> None:
    members = {"a@x.pt": {}, "b@x.pt": {}, "c@x.pt": {}}
    accounts = {
        "a@x.pt": {"must_change": 0},
        "b@x.pt": {"must_change": 1},
        "gone@x.pt": {"must_change": 0},
    }
    assert active_emails(members, accounts) == ["a@x.pt"]


def test_message_has_recipients_totals_and_pdf() -> None:
    clean = validate_report(report())
    message = build_message(clean, b"%PDF-x", "t@x.pt", ["a@x.pt", "b@x.pt"], "https://d")
    assert message["To"] == "a@x.pt, b@x.pt"
    assert "Outubro 2026" in message["Subject"]
    assert "18.450,00 €" in message.get_body().get_content()
    attachment = next(message.iter_attachments())
    assert attachment.get_filename() == "Resumo-Tesouraria-2026-10.pdf"
    assert attachment.get_content() == b"%PDF-x"
