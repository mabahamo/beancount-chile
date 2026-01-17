"""Beancount importer for Banco de Chile credit card statements."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from beancount.core import amount, data, flags
from beancount.core.number import D
from beangulp import Importer

from beancount_chile.extractors.banco_chile_credit_xls import (
    BancoChileCreditTransaction,
    BancoChileCreditXLSExtractor,
    StatementType,
)
from beancount_chile.helpers import clean_narration, normalize_payee


class BancoChileCreditImporter(Importer):
    """Importer for Banco de Chile credit card XLS/XLSX statements."""

    def __init__(
        self,
        card_last_four: str,
        account_name: str,
        currency: str = "CLP",
        file_encoding: str = "utf-8",
    ):
        """
        Initialize the Banco de Chile credit card importer.

        Args:
            card_last_four: Last 4 digits of the card (e.g., "1234")
            account_name: Beancount account name
                (e.g., "Liabilities:CreditCard:BancoChile")
            currency: Currency code (default: CLP)
            file_encoding: File encoding (default: utf-8)
        """
        self.card_last_four = card_last_four
        self.account_name = account_name
        self.currency = currency
        self.file_encoding = file_encoding
        self.extractor = BancoChileCreditXLSExtractor()

    def identify(self, filepath: Path) -> bool:
        """
        Identify if this file can be processed by this importer.

        Args:
            filepath: Path to the file

        Returns:
            True if the file can be processed, False otherwise
        """
        # Convert to Path if string (beangulp may pass strings)
        if isinstance(filepath, str):
            filepath = Path(filepath)

        # Check file extension
        if filepath.suffix.lower() not in [".xls", ".xlsx"]:
            return False

        try:
            # Try to extract metadata
            metadata, _ = self.extractor.extract(str(filepath))

            # Check if card last 4 digits match
            return metadata.card_last_four == self.card_last_four

        except (ValueError, Exception):
            return False

    def account(self, filepath: Path) -> str:
        """
        Return the account name for this file.

        Args:
            filepath: Path to the file

        Returns:
            Beancount account name
        """
        return self.account_name

    def date(self, filepath: Path) -> Optional[datetime]:
        """
        Extract the statement date from the file.

        Args:
            filepath: Path to the file

        Returns:
            Statement date
        """
        try:
            metadata, _ = self.extractor.extract(str(filepath))
            return metadata.statement_date
        except Exception:
            return None

    def filename(self, filepath: Path) -> Optional[str]:
        """
        Generate a standardized filename for this statement.

        Args:
            filepath: Path to the file

        Returns:
            Suggested filename
        """
        try:
            metadata, _ = self.extractor.extract(str(filepath))
            date_str = metadata.statement_date.strftime("%Y-%m-%d")
            statement_type = (
                "facturado"
                if metadata.statement_type == StatementType.FACTURADO
                else "no_facturado"
            )
            filename = (
                f"{date_str}_banco_chile_credit_"
                f"{self.card_last_four}_{statement_type}.xls"
            )
            return filename
        except Exception:
            return None

    def extract(
        self, filepath: Path, existing: Optional[data.Entries] = None
    ) -> data.Entries:
        """
        Extract transactions from the file.

        Args:
            filepath: Path to the file
            existing: Existing entries (for de-duplication)

        Returns:
            List of Beancount entries
        """
        metadata, transactions = self.extractor.extract(str(filepath))

        entries = []

        # Add a note about the statement type and details
        statement_note = self._create_statement_note(metadata, filepath)
        if statement_note:
            entries.append(statement_note)

        # Process transactions
        for transaction in transactions:
            entry = self._create_transaction_entry(transaction, metadata, filepath)
            if entry:
                entries.append(entry)

        return entries

    def _create_statement_note(self, metadata, filepath: Path) -> Optional[data.Note]:
        """Create a note entry about the statement."""
        statement_type = (
            "FACTURADO (Billed)"
            if metadata.statement_type == StatementType.FACTURADO
            else "NO FACTURADO (Unbilled)"
        )

        note_lines = [f"Credit Card Statement - {statement_type}"]

        if metadata.statement_type == StatementType.FACTURADO:
            if metadata.total_billed:
                note_lines.append(
                    f"Total Billed: ${metadata.total_billed:,} {self.currency}"
                )
            if metadata.minimum_payment:
                note_lines.append(
                    f"Minimum Payment: ${metadata.minimum_payment:,} {self.currency}"
                )
            if metadata.due_date:
                note_lines.append(f"Due Date: {metadata.due_date.strftime('%Y-%m-%d')}")
        else:
            if metadata.available_credit:
                note_lines.append(
                    f"Available Credit: ${metadata.available_credit:,} {self.currency}"
                )
            if metadata.total_credit_limit:
                note_lines.append(
                    f"Total Limit: ${metadata.total_credit_limit:,} {self.currency}"
                )

        note_text = " | ".join(note_lines)

        return data.Note(
            meta=data.new_metadata(str(filepath), 0),
            date=metadata.statement_date.date(),
            account=self.account_name,
            comment=note_text,
            tags=set(),
            links=set(),
        )

    def _create_transaction_entry(
        self, transaction: BancoChileCreditTransaction, metadata, filepath: Path
    ) -> Optional[data.Transaction]:
        """
        Create a Beancount transaction from a credit card transaction.

        Args:
            transaction: Credit card transaction
            metadata: Statement metadata
            filepath: Source file path

        Returns:
            Beancount transaction entry
        """
        # Credit card charges are positive (increase liability)
        txn_amount = D(str(transaction.amount))

        # Extract payee and narration
        payee = normalize_payee(transaction.description)
        narration = clean_narration(transaction.description)

        # Create metadata
        meta = data.new_metadata(str(filepath), 0)

        # Add statement type
        if metadata.statement_type == StatementType.FACTURADO:
            meta["statement_type"] = "facturado"
            if transaction.category:
                meta["category"] = transaction.category
        else:
            meta["statement_type"] = "no_facturado"
            if transaction.city:
                meta["city"] = transaction.city

        # Add installments if present
        if transaction.installments:
            meta["installments"] = transaction.installments

        # Set flag: cleared for billed, pending for unbilled
        flag = (
            flags.FLAG_OKAY
            if metadata.statement_type == StatementType.FACTURADO
            else flags.FLAG_WARNING  # ! for pending/unbilled
        )

        # Create transaction
        txn = data.Transaction(
            meta=meta,
            date=transaction.date.date(),
            flag=flag,
            payee=payee,
            narration=narration,
            tags=set(),
            links=set(),
            postings=[
                data.Posting(
                    account=self.account_name,
                    units=amount.Amount(txn_amount, self.currency),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )

        return txn
