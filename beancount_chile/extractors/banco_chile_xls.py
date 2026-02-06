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

    @staticmethod
    def _find_value_column(df: pd.DataFrame, row_idx: int, label_col: int) -> int:
        """Find the first non-NaN column after label_col in a given row."""
        for col in range(label_col + 1, df.shape[1]):
            if not pd.isna(df.iloc[row_idx, col]):
                return col
        return label_col + 1

    @staticmethod
    def _find_header_column(df: pd.DataFrame, row_idx: int, header: str) -> int:
        """Find the column containing a specific header string in a row."""
        for col in range(df.shape[1]):
            val = df.iloc[row_idx, col]
            if not pd.isna(val) and str(val).strip().startswith(header):
                return col
        return -1

    def _extract_metadata(self, df: pd.DataFrame) -> BancoChileMetadata:
        """Extract metadata from the statement header."""
        # Find account holder (matches "Sr(a):" and "Sr(a).: " variants)
        holder_row = df[df[1].astype(str).str.strip().str.startswith("Sr(a)")]
        if holder_row.empty:
            raise ValueError("Could not find account holder information")
        holder_idx = holder_row.index[0]
        value_col = self._find_value_column(df, holder_idx, 1)
        account_holder = str(df.iloc[holder_idx, value_col])

        # Find RUT (row with "Rut:")
        rut_row = df[df[1].astype(str).str.strip().str.startswith("Rut:")]
        if rut_row.empty:
            raise ValueError("Could not find RUT information")
        rut_idx = rut_row.index[0]
        value_col = self._find_value_column(df, rut_idx, 1)
        rut = str(df.iloc[rut_idx, value_col])

        # Find account number (matches "Cuenta:" and "Cuenta N°:" variants)
        account_row = df[df[1].astype(str).str.strip().str.startswith("Cuenta")]
        if account_row.empty:
            raise ValueError("Could not find account information")
        account_idx = account_row.index[0]
        value_col = self._find_value_column(df, account_idx, 1)
        account_number = str(df.iloc[account_idx, value_col])

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

        balance_header_idx = balance_header_row.index[0]
        balance_row_idx = balance_header_idx + 1

        # Available balance is always in col 1
        available_balance = self._parse_amount(df.iloc[balance_row_idx, 1])

        # Accounting balance: find "Saldo Contable" column dynamically
        contable_col = self._find_header_column(
            df, balance_header_idx, "Saldo Contable"
        )
        if contable_col == -1:
            contable_col = 2  # fallback
        accounting_balance = self._parse_amount(df.iloc[balance_row_idx, contable_col])

        # Extract totals
        totals_header_row = df[
            df[1].astype(str).str.strip().str.startswith("Total Cargos")
        ]
        if totals_header_row.empty:
            raise ValueError("Could not find totals information")

        totals_header_idx = totals_header_row.index[0]
        totals_row_idx = totals_header_idx + 1

        # Total debits always in col 1
        total_debits = self._parse_amount(df.iloc[totals_row_idx, 1])

        # Total credits: find "Total Abonos" column dynamically
        abonos_col = self._find_header_column(df, totals_header_idx, "Total Abonos")
        if abonos_col == -1:
            abonos_col = 2  # fallback
        total_credits = self._parse_amount(df.iloc[totals_row_idx, abonos_col])

        # Extract statement date from "Movimientos al DD/MM/YYYY"
        # In XLSX: single cell "Movimientos al DD/MM/YYYY"
        # In binary XLS: split across cols, e.g. col1="Movimientos",
        # col3="al DD/MM/YYYY"
        movements_row = df[df[1].astype(str).str.strip().str.startswith("Movimientos")]
        if movements_row.empty:
            raise ValueError("Could not find statement date")

        movements_idx = movements_row.index[0]
        # Scan all columns in this row for a date pattern
        statement_date = None
        for col in range(df.shape[1]):
            cell_val = df.iloc[movements_idx, col]
            if pd.isna(cell_val):
                continue
            date_match = re.search(r"(\d{2}/\d{2}/\d{4})", str(cell_val))
            if date_match:
                statement_date = datetime.strptime(date_match.group(1), "%d/%m/%Y")
                break

        if statement_date is None:
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

    def _detect_transaction_columns(
        self, df: pd.DataFrame, header_idx: int
    ) -> dict[str, int]:
        """Detect transaction column indices from the header row.

        Returns a dict mapping column names to their indices.
        Falls back to XLSX defaults (cols 1-6) if detection fails.
        """
        col_map = {}
        header_row = df.iloc[header_idx]
        for col in range(df.shape[1]):
            val = header_row[col]
            if pd.isna(val):
                continue
            val_str = str(val).strip()
            if val_str == "Fecha":
                col_map["date"] = col
            elif val_str == "Descripción":
                col_map["description"] = col
            elif val_str.startswith("Canal"):
                col_map["channel"] = col
            elif val_str.startswith("Cargos"):
                col_map["debit"] = col
            elif val_str.startswith("Abonos"):
                col_map["credit"] = col
            elif val_str.startswith("Saldo"):
                col_map["balance"] = col

        # Fallback to XLSX defaults if header detection is incomplete
        col_map.setdefault("date", 1)
        col_map.setdefault("description", 2)
        col_map.setdefault("channel", 3)
        col_map.setdefault("debit", 4)
        col_map.setdefault("credit", 5)
        col_map.setdefault("balance", 6)

        return col_map

    def _extract_transactions(self, df: pd.DataFrame) -> list[BancoChileTransaction]:
        """Extract transactions from the statement."""
        # Find the transaction header row
        header_row = df[df[1].astype(str).str.strip().str.startswith("Fecha")]
        if header_row.empty:
            raise ValueError("Could not find transaction header")

        header_idx = header_row.index[0]
        cols = self._detect_transaction_columns(df, header_idx)

        date_col = cols["date"]
        desc_col = cols["description"]
        chan_col = cols["channel"]
        debit_col = cols["debit"]
        credit_col = cols["credit"]
        balance_col = cols["balance"]

        # Transactions start from the next row
        transactions = []
        for idx in range(header_idx + 1, len(df)):
            row = df.iloc[idx]

            # Stop if we hit an empty row or footer
            if pd.isna(row[date_col]) or row[date_col] is None:
                continue

            # Check if it's a valid date
            try:
                date_str = str(row[date_col])
                if not re.match(r"\d{2}/\d{2}/\d{4}", date_str):
                    break

                date = datetime.strptime(date_str, "%d/%m/%Y")
                description = str(row[desc_col]) if not pd.isna(row[desc_col]) else ""
                channel = str(row[chan_col]) if not pd.isna(row[chan_col]) else ""

                debit = (
                    self._parse_amount(row[debit_col])
                    if not pd.isna(row[debit_col])
                    else None
                )
                credit = (
                    self._parse_amount(row[credit_col])
                    if not pd.isna(row[credit_col])
                    else None
                )
                balance = self._parse_amount(row[balance_col])

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
