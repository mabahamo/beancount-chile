"""Beancount importer for Banco de Chile account statements."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from beancount.core import data, amount, flags
from beancount.core.number import D
from beangulp import Importer

from beancount_chile.extractors.banco_chile_xls import (
    BancoChileXLSExtractor,
    BancoChileTransaction,
)
from beancount_chile.helpers import normalize_payee, clean_narration


class BancoChileImporter(Importer):
    """Importer for Banco de Chile XLS/XLSX account statements (cartola)."""

    def __init__(
        self,
        account_number: str,
        account_name: str,
        currency: str = "CLP",
        file_encoding: str = "utf-8",
    ):
        """
        Initialize the Banco de Chile importer.

        Args:
            account_number: Bank account number (e.g., "00-123-45678-90")
            account_name: Beancount account name (e.g., "Assets:BancoChile:Checking")
            currency: Currency code (default: CLP)
            file_encoding: File encoding (default: utf-8)
        """
        self.account_number = account_number
        self.account_name = account_name
        self.currency = currency
        self.file_encoding = file_encoding
        self.extractor = BancoChileXLSExtractor()

    def identify(self, filepath: Path) -> bool:
        """
        Identify if this file can be processed by this importer.

        Args:
            filepath: Path to the file

        Returns:
            True if the file can be processed, False otherwise
        """
        # Check file extension
        if filepath.suffix.lower() not in [".xls", ".xlsx"]:
            return False

        try:
            # Try to extract metadata
            metadata, _ = self.extractor.extract(str(filepath))

            # Check if account number matches
            return metadata.account_number == self.account_number

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
            return f"{date_str}_banco_chile_{self.account_number.replace('-', '')}.xls"
        except Exception:
            return None

    def extract(self, filepath: Path, existing: Optional[data.Entries] = None) -> data.Entries:
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

        # Add a balance assertion at the end of the statement
        if transactions:
            last_transaction = transactions[-1]
            balance_entry = data.Balance(
                meta=data.new_metadata(str(filepath), 0),
                date=last_transaction.date.date(),
                account=self.account_name,
                amount=amount.Amount(D(str(last_transaction.balance)), self.currency),
                tolerance=None,
                diff_amount=None,
            )
            entries.append(balance_entry)

        # Process transactions in reverse order (oldest first)
        for transaction in reversed(transactions):
            entry = self._create_transaction_entry(transaction, filepath)
            if entry:
                entries.append(entry)

        return entries

    def _create_transaction_entry(
        self, transaction: BancoChileTransaction, filepath: Path
    ) -> Optional[data.Transaction]:
        """
        Create a Beancount transaction from a Banco de Chile transaction.

        Args:
            transaction: Banco de Chile transaction
            filepath: Source file path

        Returns:
            Beancount transaction entry
        """
        # Determine amount and posting direction
        if transaction.debit and transaction.debit > 0:
            # Debit (money out)
            txn_amount = -D(str(transaction.debit))
        elif transaction.credit and transaction.credit > 0:
            # Credit (money in)
            txn_amount = D(str(transaction.credit))
        else:
            # No amount, skip
            return None

        # Extract payee and narration
        payee = normalize_payee(transaction.description)
        narration = clean_narration(transaction.description)

        # Add channel information to metadata
        meta = data.new_metadata(str(filepath), 0)
        meta["channel"] = transaction.channel

        # Create transaction
        txn = data.Transaction(
            meta=meta,
            date=transaction.date.date(),
            flag=flags.FLAG_OKAY,
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
