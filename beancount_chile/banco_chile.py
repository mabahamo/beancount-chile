"""Beancount importer for Banco de Chile account statements."""

from datetime import date as date_type
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Union

from beancount.core import amount, data, flags
from beancount.core.number import D
from beangulp import Importer

from beancount_chile.extractors.banco_chile_pdf import BancoChilePDFExtractor
from beancount_chile.extractors.banco_chile_xls import (
    BancoChileTransaction,
    BancoChileXLSExtractor,
)
from beancount_chile.helpers import clean_narration, normalize_payee

# Type alias for categorizer return value
# Can return:
# - None: no categorization, no subaccount
# - str: single category account (no subaccount)
# - List[Tuple[str, Decimal]]: multiple postings (no subaccount)
# - Tuple[str, str]: (subaccount_suffix, category_account)
# - Tuple[str, List[Tuple[str, Decimal]]]: (subaccount, splits)
# - Tuple[str, None]: (subaccount_suffix, no category)
CategorizerReturn = Optional[
    Union[
        str,
        List[Tuple[str, Decimal]],
        Tuple[str, Optional[Union[str, List[Tuple[str, Decimal]]]]],
    ]
]

# Type for the categorizer callable
CategorizerFunc = Callable[[date_type, str, str, Decimal, dict], CategorizerReturn]


class BancoChileImporter(Importer):
    """Importer for Banco de Chile account statements (cartola).

    Supports XLS/XLSX/PDF formats.
    """

    def __init__(
        self,
        account_number: str,
        account_name: str,
        currency: str = "CLP",
        file_encoding: str = "utf-8",
        categorizer: Optional[CategorizerFunc] = None,
    ):
        """
        Initialize the Banco de Chile importer.

        Args:
            account_number: Bank account number (e.g., "00-123-45678-90")
            account_name: Beancount account name
                (e.g., "Assets:BancoChile:Checking")
            currency: Currency code (default: CLP)
            file_encoding: File encoding (default: utf-8)
            categorizer: Optional callable that takes (date, payee, narration,
                amount, metadata) and returns:
                - None for no categorization, no subaccount
                - str (account name) for single posting, no subaccount
                - List[Tuple[str, Decimal]] for split postings, no subaccount
                - Tuple[str, str] for (subaccount_suffix, category_account)
                - Tuple[str, List[Tuple[str, Decimal]]] for (subaccount, splits)
                - Tuple[str, None] for subaccount only, no category
        """
        self.account_number = account_number
        self.account_name = account_name
        self.currency = currency
        self.file_encoding = file_encoding
        self.categorizer = categorizer
        self.xls_extractor = BancoChileXLSExtractor()
        self.pdf_extractor = BancoChilePDFExtractor()

    def _get_extractor(
        self, filepath: Path
    ) -> Optional[Union[BancoChileXLSExtractor, BancoChilePDFExtractor]]:
        """
        Get the appropriate extractor based on file extension.

        Args:
            filepath: Path to the file

        Returns:
            Extractor instance or None if unsupported format
        """
        # Convert to Path if string (beangulp may pass strings)
        if isinstance(filepath, str):
            filepath = Path(filepath)
        suffix = filepath.suffix.lower()
        if suffix in [".xls", ".xlsx"]:
            return self.xls_extractor
        elif suffix == ".pdf":
            return self.pdf_extractor
        else:
            return None

    def identify(self, filepath: Path) -> bool:
        """
        Identify if this file can be processed by this importer.

        Args:
            filepath: Path to the file

        Returns:
            True if the file can be processed, False otherwise
        """
        # Get appropriate extractor based on file extension
        extractor = self._get_extractor(filepath)
        if not extractor:
            return False

        try:
            # Try to extract metadata
            metadata, _ = extractor.extract(str(filepath))

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
        extractor = self._get_extractor(filepath)
        if not extractor:
            return None

        try:
            metadata, _ = extractor.extract(str(filepath))
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
        extractor = self._get_extractor(filepath)
        if not extractor:
            return None

        try:
            metadata, _ = extractor.extract(str(filepath))
            date_str = metadata.statement_date.strftime("%Y-%m-%d")
            ext = filepath.suffix.lower()
            account_clean = self.account_number.replace("-", "")
            return f"{date_str}_banco_chile_{account_clean}{ext}"
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
        extractor = self._get_extractor(filepath)
        if not extractor:
            return []

        metadata, transactions = extractor.extract(str(filepath))

        entries = []

        # Add a balance assertion at the end of the statement
        # Use metadata.accounting_balance (SALDO FINAL) instead of
        # last_transaction.balance which can be 0 for PDF files
        # Balance assertions in Beancount check the balance at the BEGINNING of
        # the specified date, so we set the date to the day AFTER the statement
        # date to verify the final balance after all transactions
        if metadata.accounting_balance:
            balance_amount = D(str(metadata.accounting_balance))
            balance_date = metadata.statement_date.date() + timedelta(days=1)
            balance_entry = data.Balance(
                meta=data.new_metadata(str(filepath), 0),
                date=balance_date,
                account=self.account_name,
                amount=amount.Amount(balance_amount, self.currency),
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

        # Prepare metadata for categorizer and account_modifier
        categorizer_metadata = {
            "channel": transaction.channel,
            "debit": transaction.debit,
            "credit": transaction.credit,
            "balance": transaction.balance,
        }

        # Call categorizer if provided
        category_result = None
        subaccount_suffix = None
        if self.categorizer:
            raw_result = self.categorizer(
                transaction.date.date(),
                payee,
                narration,
                txn_amount,
                categorizer_metadata,
            )

            # Check if categorizer returned a tuple with (subaccount, category/splits)
            if isinstance(raw_result, tuple) and len(raw_result) == 2:
                subaccount_suffix, category_result = raw_result
            else:
                category_result = raw_result

        # Determine the account name with optional subaccount
        account_name = self.account_name
        if subaccount_suffix:
            account_name = f"{self.account_name}:{subaccount_suffix}"

        # Prepare postings list with the (possibly modified) account name
        postings = [
            data.Posting(
                account=account_name,
                units=amount.Amount(txn_amount, self.currency),
                cost=None,
                price=None,
                flag=None,
                meta=None,
            ),
        ]

        # Add categorization postings if categorizer returned a result
        if category_result:
            # Handle both string and list returns
            if isinstance(category_result, str):
                # Single category account (backward compatible)
                postings.append(
                    data.Posting(
                        account=category_result,
                        units=amount.Amount(-txn_amount, self.currency),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    )
                )
            elif isinstance(category_result, list):
                # Multiple split postings
                for category_account, category_amount in category_result:
                    postings.append(
                        data.Posting(
                            account=category_account,
                            units=amount.Amount(category_amount, self.currency),
                            cost=None,
                            price=None,
                            flag=None,
                            meta=None,
                        )
                    )

        # Create transaction
        txn = data.Transaction(
            meta=meta,
            date=transaction.date.date(),
            flag=flags.FLAG_OKAY,
            payee=payee,
            narration=narration,
            tags=set(),
            links=set(),
            postings=postings,
        )

        return txn
