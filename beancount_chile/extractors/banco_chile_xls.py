"""Extractor for Banco de Chile XLS/XLSX account statements (cartola)."""

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

import pandas as pd


@dataclass
class BancoChileMetadata:
    """Metadata extracted from Banco de Chile statement."""

    account_holder: str
    rut: str
    account_number: str
    currency: str
    available_balance: Decimal
    accounting_balance: Decimal
    total_debits: Decimal
    total_credits: Decimal
    statement_date: datetime


@dataclass
class BancoChileTransaction:
    """A transaction from Banco de Chile statement."""

    date: datetime
    description: str
    channel: str
    debit: Optional[Decimal]
    credit: Optional[Decimal]
    balance: Decimal


class BancoChileXLSExtractor:
    """Extract transactions from Banco de Chile XLS/XLSX files."""

    # Expected column names for transactions
    EXPECTED_COLUMNS = [
        "Fecha",
        "Descripción",
        "Canal o Sucursal",
        "Cargos (CLP)",
        "Abonos (CLP)",
        "Saldo (CLP)",
    ]

    def __init__(self):
        """Initialize the extractor."""
        pass

    def _detect_excel_engine(self, filepath: str) -> str:
        """
        Detect the appropriate pandas engine based on file content.

        Args:
            filepath: Path to the Excel file

        Returns:
            Engine name: "xlrd" for old XLS, "openpyxl" for XLSX
        """
        # Read the first 4 bytes to check the file signature
        with open(filepath, "rb") as f:
            signature = f.read(4)

        # XLSX files are ZIP files (start with 'PK')
        # Old XLS files start with different signatures (e.g., 0xD0CF for OLE2)
        if signature[:2] == b"PK":
            return "openpyxl"
        else:
            return "xlrd"

    def extract(
        self, filepath: str
    ) -> tuple[BancoChileMetadata, list[BancoChileTransaction]]:
        """
        Extract metadata and transactions from a Banco de Chile statement.

        Args:
            filepath: Path to the XLS/XLSX file

        Returns:
            Tuple of (metadata, transactions)

        Raises:
            ValueError: If the file format is invalid
        """
        # Read the entire file without headers
        # Auto-detect engine based on file content (not extension)
        engine = self._detect_excel_engine(filepath)
        df = pd.read_excel(filepath, header=None, engine=engine)

        # Extract metadata
        metadata = self._extract_metadata(df)

        # Extract transactions
        transactions = self._extract_transactions(df)

        return metadata, transactions

    def _extract_metadata(self, df: pd.DataFrame) -> BancoChileMetadata:
        """Extract metadata from the statement header."""
        # Find account holder (row with "Sr(a):")
        holder_row = df[df[1].astype(str).str.strip().str.startswith("Sr(a):")]
        if holder_row.empty:
            raise ValueError("Could not find account holder information")
        account_holder = str(holder_row.iloc[0, 2])

        # Find RUT (row with "Rut:")
        rut_row = df[df[1].astype(str).str.strip().str.startswith("Rut:")]
        if rut_row.empty:
            raise ValueError("Could not find RUT information")
        rut = str(rut_row.iloc[0, 2])

        # Find account number (row with "Cuenta:")
        account_row = df[df[1].astype(str).str.strip().str.startswith("Cuenta:")]
        if account_row.empty:
            raise ValueError("Could not find account information")
        account_number = str(account_row.iloc[0, 2])

        # Find currency (row with "Moneda:")
        currency_row = df[df[1].astype(str).str.strip().str.startswith("Moneda:")]
        if currency_row.empty:
            raise ValueError("Could not find currency information")
        # Always use CLP for Chilean pesos
        currency = "CLP"

        # Extract balance information
        balance_header_row = df[
            df[1].astype(str).str.strip().str.startswith("Saldo Disponible")
        ]
        if balance_header_row.empty:
            raise ValueError("Could not find balance information")

        balance_row_idx = balance_header_row.index[0] + 1
        available_balance = self._parse_amount(df.iloc[balance_row_idx, 1])
        accounting_balance = self._parse_amount(df.iloc[balance_row_idx, 2])

        # Extract totals
        totals_header_row = df[
            df[1].astype(str).str.strip().str.startswith("Total Cargos")
        ]
        if totals_header_row.empty:
            raise ValueError("Could not find totals information")

        totals_row_idx = totals_header_row.index[0] + 1
        total_debits = self._parse_amount(df.iloc[totals_row_idx, 1])
        total_credits = self._parse_amount(df.iloc[totals_row_idx, 2])

        # Extract statement date from "Movimientos al DD/MM/YYYY"
        movements_row = df[df[1].astype(str).str.contains("Movimientos al", na=False)]
        if movements_row.empty:
            raise ValueError("Could not find statement date")

        movements_text = str(movements_row.iloc[0, 1])
        date_match = re.search(r"(\d{2}/\d{2}/\d{4})", movements_text)
        if date_match:
            statement_date = datetime.strptime(date_match.group(1), "%d/%m/%Y")
        else:
            statement_date = datetime.now()

        return BancoChileMetadata(
            account_holder=account_holder,
            rut=rut,
            account_number=account_number,
            currency=currency,
            available_balance=available_balance,
            accounting_balance=accounting_balance,
            total_debits=total_debits,
            total_credits=total_credits,
            statement_date=statement_date,
        )

    def _extract_transactions(self, df: pd.DataFrame) -> list[BancoChileTransaction]:
        """Extract transactions from the statement."""
        # Find the transaction header row
        header_row = df[df[1].astype(str).str.strip().str.startswith("Fecha")]
        if header_row.empty:
            raise ValueError("Could not find transaction header")

        header_idx = header_row.index[0]

        # Transactions start from the next row
        transactions = []
        for idx in range(header_idx + 1, len(df)):
            row = df.iloc[idx]

            # Stop if we hit an empty row or footer
            if pd.isna(row[1]) or row[1] is None:
                continue

            # Check if it's a valid date
            try:
                date_str = str(row[1])
                if not re.match(r"\d{2}/\d{2}/\d{4}", date_str):
                    break

                date = datetime.strptime(date_str, "%d/%m/%Y")
                description = str(row[2]) if not pd.isna(row[2]) else ""
                channel = str(row[3]) if not pd.isna(row[3]) else ""

                debit = self._parse_amount(row[4]) if not pd.isna(row[4]) else None
                credit = self._parse_amount(row[5]) if not pd.isna(row[5]) else None
                balance = self._parse_amount(row[6])

                transaction = BancoChileTransaction(
                    date=date,
                    description=description,
                    channel=channel,
                    debit=debit,
                    credit=credit,
                    balance=balance,
                )
                transactions.append(transaction)

            except (ValueError, AttributeError):
                # Not a valid transaction row, stop processing
                break

        return transactions

    @staticmethod
    def _parse_amount(value) -> Decimal:
        """Parse an amount from the spreadsheet."""
        if pd.isna(value):
            return Decimal("0")

        # Handle numeric values
        if isinstance(value, (int, float)):
            return Decimal(str(value))

        # Handle string values (remove commas, periods for thousands)
        value_str = str(value).replace(",", "").replace(".", "").strip()
        if not value_str:
            return Decimal("0")

        try:
            return Decimal(value_str)
        except Exception:
            return Decimal("0")
