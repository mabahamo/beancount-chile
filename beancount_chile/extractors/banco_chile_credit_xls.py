"""Extractor for Banco de Chile credit card XLS/XLSX statements."""

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

import pandas as pd


class StatementType(Enum):
    """Type of credit card statement."""

    FACTURADO = "facturado"  # Billed/settled transactions
    NO_FACTURADO = "no_facturado"  # Unbilled/pending transactions


@dataclass
class BancoChileCreditMetadata:
    """Metadata extracted from Banco de Chile credit card statement."""

    account_holder: str
    rut: str
    card_type: str
    card_last_four: str
    card_status: str
    statement_type: StatementType
    statement_date: datetime

    # Facturado-specific fields
    total_billed: Optional[Decimal] = None
    minimum_payment: Optional[Decimal] = None
    billing_date: Optional[datetime] = None
    due_date: Optional[datetime] = None

    # No Facturado-specific fields
    available_credit: Optional[Decimal] = None
    used_credit: Optional[Decimal] = None
    total_credit_limit: Optional[Decimal] = None


@dataclass
class BancoChileCreditTransaction:
    """A transaction from Banco de Chile credit card statement."""

    date: datetime
    description: str
    amount: Decimal

    # Common fields
    installments: Optional[str] = None  # e.g., "01/01"

    # Facturado-specific fields
    category: Optional[str] = None  # e.g., "Total de Pagos, Compras..."

    # No Facturado-specific fields
    card_type: Optional[str] = None  # e.g., "Titular********1234"
    city: Optional[str] = None


class BancoChileCreditXLSExtractor:
    """Extract transactions from Banco de Chile credit card XLS/XLSX files."""

    def __init__(self):
        """Initialize the extractor."""
        pass

    def extract(
        self, filepath: str
    ) -> tuple[BancoChileCreditMetadata, list[BancoChileCreditTransaction]]:
        """
        Extract metadata and transactions from a Banco de Chile credit card statement.

        Args:
            filepath: Path to the XLS/XLSX file

        Returns:
            Tuple of (metadata, transactions)

        Raises:
            ValueError: If the file format is invalid
        """
        # Read the entire file without headers
        df = pd.read_excel(filepath, header=None, engine="openpyxl")

        # Detect statement type
        statement_type = self._detect_statement_type(df)

        # Extract metadata
        metadata = self._extract_metadata(df, statement_type)

        # Extract transactions
        transactions = self._extract_transactions(df, statement_type)

        return metadata, transactions

    def _detect_statement_type(self, df: pd.DataFrame) -> StatementType:
        """Detect whether this is a billed or unbilled statement."""
        # Look for distinctive text
        for idx in range(min(20, len(df))):
            row = df.iloc[idx]
            for cell in row:
                if pd.notna(cell) and isinstance(cell, str):
                    if "Movimientos Facturados" in cell:
                        return StatementType.FACTURADO
                    if "Saldos y Movimientos No Facturados" in cell:
                        return StatementType.NO_FACTURADO

        raise ValueError("Could not determine statement type")

    def _extract_metadata(
        self, df: pd.DataFrame, statement_type: StatementType
    ) -> BancoChileCreditMetadata:
        """Extract metadata from the statement header."""
        # Find account holder (row with "Sr(a).:")
        holder_row = df[df[1] == "Sr(a).: "]
        if holder_row.empty:
            raise ValueError("Could not find account holder information")
        account_holder = str(holder_row.iloc[0, 2])

        # Find RUT (row with "Rut:")
        rut_row = df[df[1] == "Rut:"]
        if rut_row.empty:
            raise ValueError("Could not find RUT information")
        rut = str(rut_row.iloc[0, 2])

        # Find card type (row with "Tipo de Tarjeta:")
        card_row = df[df[1] == "Tipo de Tarjeta:"]
        if card_row.empty:
            raise ValueError("Could not find card type information")
        card_type = str(card_row.iloc[0, 2])

        # Extract last 4 digits from card type
        card_match = re.search(r"\*+(\d{4})", card_type)
        if card_match:
            card_last_four = card_match.group(1)
        else:
            card_last_four = "0000"

        # Find status (row with "Estado:")
        status_row = df[df[1] == "Estado:"]
        if status_row.empty:
            raise ValueError("Could not find status information")
        card_status = str(status_row.iloc[0, 2])

        # Extract statement date
        statement_date = datetime.now()
        if statement_type == StatementType.FACTURADO:
            # Look for billing date
            billing_header_row = df[df[1] == "Monto Facturado"]
            if not billing_header_row.empty:
                billing_data_idx = billing_header_row.index[0] + 1
                if billing_data_idx < len(df):
                    billing_date_str = str(df.iloc[billing_data_idx, 5])
                    if re.match(r"\d{2}/\d{2}/\d{4}", billing_date_str):
                        statement_date = datetime.strptime(billing_date_str, "%d/%m/%Y")
        else:
            # Look for date in "Saldos y Movimientos No Facturados al DD/MM/YYYY"
            header_row = df[
                df[1]
                .astype(str)
                .str.contains("Saldos y Movimientos No Facturados", na=False)
            ]
            if not header_row.empty:
                for col in range(len(df.columns)):
                    cell_value = header_row.iloc[0, col]
                    if pd.notna(cell_value):
                        date_match = re.search(r"(\d{2}/\d{2}/\d{4})", str(cell_value))
                        if date_match:
                            statement_date = datetime.strptime(
                                date_match.group(1), "%d/%m/%Y"
                            )
                            break

        metadata = BancoChileCreditMetadata(
            account_holder=account_holder,
            rut=rut,
            card_type=card_type,
            card_last_four=card_last_four,
            card_status=card_status,
            statement_type=statement_type,
            statement_date=statement_date,
        )

        # Extract type-specific metadata
        if statement_type == StatementType.FACTURADO:
            self._extract_facturado_metadata(df, metadata)
        else:
            self._extract_no_facturado_metadata(df, metadata)

        return metadata

    def _extract_facturado_metadata(
        self, df: pd.DataFrame, metadata: BancoChileCreditMetadata
    ) -> None:
        """Extract metadata specific to billed statements."""
        # Find billing summary row
        billing_header_row = df[df[1] == "Monto Facturado"]
        if billing_header_row.empty:
            return

        billing_data_idx = billing_header_row.index[0] + 1
        if billing_data_idx >= len(df):
            return

        # Extract billing data
        billing_row = df.iloc[billing_data_idx]

        # Total billed (column B)
        metadata.total_billed = self._parse_amount(billing_row[1])

        # Minimum payment (column D)
        metadata.minimum_payment = self._parse_amount(billing_row[3])

        # Billing date (column F)
        if pd.notna(billing_row[5]):
            try:
                metadata.billing_date = datetime.strptime(
                    str(billing_row[5]), "%d/%m/%Y"
                )
            except ValueError:
                pass

        # Due date (column I or J)
        for col in [8, 9]:
            if pd.notna(billing_row[col]):
                try:
                    metadata.due_date = datetime.strptime(
                        str(billing_row[col]), "%d/%m/%Y"
                    )
                    break
                except ValueError:
                    continue

    def _extract_no_facturado_metadata(
        self, df: pd.DataFrame, metadata: BancoChileCreditMetadata
    ) -> None:
        """Extract metadata specific to unbilled statements."""
        # Find credit limit row
        credit_header_row = df[df[1] == "Cupo Disponible"]
        if credit_header_row.empty:
            return

        credit_data_idx = credit_header_row.index[0] + 1
        if credit_data_idx >= len(df):
            return

        # Extract credit data
        credit_row = df.iloc[credit_data_idx]

        # Available credit (column B)
        metadata.available_credit = self._parse_amount(credit_row[1])

        # Used credit (column E)
        metadata.used_credit = self._parse_amount(credit_row[4])

        # Total credit limit (column H)
        metadata.total_credit_limit = self._parse_amount(credit_row[7])

    def _extract_transactions(
        self, df: pd.DataFrame, statement_type: StatementType
    ) -> list[BancoChileCreditTransaction]:
        """Extract transactions from the statement."""
        # Find the transaction header row (look for "Movimientos Nacionales")
        movimientos_row = df[df[1] == "Movimientos Nacionales"]
        if movimientos_row.empty:
            raise ValueError("Could not find transaction section")

        # Transaction headers are in the next row
        header_idx = movimientos_row.index[0] + 1

        # Transactions start from the row after headers
        transactions = []
        for idx in range(header_idx + 1, len(df)):
            row = df.iloc[idx]

            # Stop if we hit an empty row
            if pd.isna(row[1]):
                continue

            try:
                if statement_type == StatementType.FACTURADO:
                    transaction = self._parse_facturado_transaction(row)
                else:
                    transaction = self._parse_no_facturado_transaction(row)

                if transaction:
                    transactions.append(transaction)

            except (ValueError, AttributeError):
                # Not a valid transaction row, skip
                continue

        return transactions

    def _parse_facturado_transaction(
        self, row: pd.Series
    ) -> Optional[BancoChileCreditTransaction]:
        """Parse a transaction from a billed statement."""
        # Column B: Category
        category = str(row[1]) if pd.notna(row[1]) else None

        # Column C: Date
        date_str = str(row[2])
        if not re.match(r"\d{2}/\d{2}/\d{4}", date_str):
            return None
        date = datetime.strptime(date_str, "%d/%m/%Y")

        # Column D: Description
        description = str(row[3]) if pd.notna(row[3]) else ""

        # Column G: Installments
        installments = str(row[6]) if pd.notna(row[6]) else None

        # Column H: Amount
        amount = self._parse_amount(row[7])
        if amount == Decimal("0"):
            return None

        return BancoChileCreditTransaction(
            date=date,
            description=description,
            amount=amount,
            installments=installments,
            category=category,
        )

    def _parse_no_facturado_transaction(
        self, row: pd.Series
    ) -> Optional[BancoChileCreditTransaction]:
        """Parse a transaction from an unbilled statement."""
        # Column B: Date
        date_str = str(row[1])
        if not re.match(r"\d{2}/\d{2}/\d{4}", date_str):
            return None
        date = datetime.strptime(date_str, "%d/%m/%Y")

        # Column C: Card type
        card_type = str(row[2]) if pd.notna(row[2]) else None

        # Column E: Description
        description = str(row[4]) if pd.notna(row[4]) else ""

        # Column G: City
        city = str(row[6]) if pd.notna(row[6]) else None

        # Column H: Installments
        installments = str(row[7]) if pd.notna(row[7]) else None

        # Column K (index 10): Amount
        amount = self._parse_amount(row[10])
        if amount == Decimal("0"):
            return None

        return BancoChileCreditTransaction(
            date=date,
            description=description,
            amount=amount,
            installments=installments,
            card_type=card_type,
            city=city,
        )

    @staticmethod
    def _parse_amount(value) -> Decimal:
        """Parse an amount from the spreadsheet."""
        if pd.isna(value):
            return Decimal("0")

        # Handle numeric values
        if isinstance(value, (int, float)):
            return Decimal(str(int(value)))

        # Handle string values (remove commas, periods for thousands)
        value_str = str(value).replace(",", "").replace(".", "").strip()
        if not value_str or value_str == "nan":
            return Decimal("0")

        try:
            return Decimal(value_str)
        except Exception:
            return Decimal("0")
