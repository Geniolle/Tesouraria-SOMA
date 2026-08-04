"""
Transaction data model for MT940 processing.

Represents a single bank transaction extracted from MT940 format.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Transaction(BaseModel):
    """Single bank transaction from MT940 file."""

    data_mov: str = Field(..., description="Movement date (DD/MM/YYYY)")
    data_valor: str = Field(..., description="Value date (DD/MM/YYYY)")
    descricao: str = Field(..., description="Transaction description")
    valor: Decimal = Field(..., description="Transaction amount")
    tipo: str = Field(..., description="Transaction type (Entrada/Saída/etc)")
    timestamp: Optional[str] = Field(None, description="Processing timestamp")
    id_interno: Optional[str] = Field(None, description="Internal ID (EXT+10digits)")
    saldo_contabilistico: Optional[Decimal] = Field(None, description="Final balance")

    model_config = {"use_enum_values": True}

    @field_validator("valor", mode="before")
    @classmethod
    def validate_valor(cls, v) -> Decimal:
        """Ensure valor is a valid Decimal."""
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            return Decimal(v.replace(",", "."))
        raise ValueError(f"Invalid valor format: {v}")

    @field_validator("descricao")
    @classmethod
    def validate_descricao(cls, v: str) -> str:
        """Normalize description."""
        return v.strip() if v else ""

    def dedup_key(self) -> str:
        """
        Generate a unique key for deduplication.

        Format: DATA_MOV|DESCRICAO|VALOR
        """
        return f"{self.data_mov}|{self.descricao}|{self.valor}"


class MT940Header(BaseModel):
    """MT940 file header information."""

    data_mov: str = Field(..., description="Opening balance date")
    saldo_abertura: Decimal = Field(..., description="Opening balance")


class MT940Footer(BaseModel):
    """MT940 file footer information."""

    data_fecho: str = Field(..., description="Closing balance date")
    saldo_fecho: Decimal = Field(..., description="Closing balance")


class MT940File(BaseModel):
    """Complete MT940 file parsed."""

    filename: str = Field(..., description="Original filename")
    header: MT940Header
    transactions: list[Transaction] = Field(default_factory=list)
    footer: MT940Footer
    total_transactions: int = Field(default=0)

    def __init__(self, **data):
        """Initialize and calculate transaction count."""
        super().__init__(**data)
        self.total_transactions = len(self.transactions)
