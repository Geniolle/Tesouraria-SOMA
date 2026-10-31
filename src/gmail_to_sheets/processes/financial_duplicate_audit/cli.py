"""Manual dry-run CLI for the financial duplicate audit."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from src.gmail_to_sheets.clients.sheets_client import SheetsClient
from src.gmail_to_sheets.config.settings import load_settings

from .report import write_reports
from .runner import FinancialDuplicateAuditRunner


def _month(value: str) -> int:
    month = int(value)
    if month < 1 or month > 12:
        raise argparse.ArgumentTypeError("mes must be between 1 and 12")
    return month


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Auditoria financeira de duplicados em modo somente leitura")
    parser.add_argument("--ano", type=int, required=True)
    parser.add_argument("--mes", type=_month, required=True)
    parser.add_argument("--dry-run", action="store_true", required=True)
    return parser


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    settings_loader: Callable[[], Any] = load_settings,
    client_factory: Callable[[Path], Any] = SheetsClient,
    runner_factory: Callable[..., Any] = FinancialDuplicateAuditRunner,
) -> int:
    args = build_parser().parse_args(argv)
    settings = settings_loader()
    client = client_factory(settings.sheets.service_account_path)
    runner = runner_factory(
        client,
        settings.sheets.spreadsheet_id,
        verbo_cafe_spreadsheet_id=settings.verbo_cafe.source_spreadsheet_id,
    )
    result = runner.run(year=args.ano, month=args.mes)
    output_dir = Path("logs/financial_duplicate_audit") / f"{args.ano:04d}-{args.mes:02d}"
    paths = write_reports(result, output_dir)
    print(f"DRY_RUN concluído: {len(result.findings)} ocorrências; relatório {paths['json']}")
    return 0


def main() -> int:
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
