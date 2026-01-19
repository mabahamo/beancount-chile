"""Beancount importer for Banco de Chile account statements."""

import hashlib
from datetime import date as date_type
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

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
# Returns a dict with optional fields:
# - category: str - single category account
# - payee: str - override transaction payee
# - narration: str - override transaction narration
# - subaccount: str - subaccount suffix for main account
# - postings: List[Dict] - for splits, each with 'category' and 'amount'
# - receipts: List[str] - list of paths to receipt files
CategorizerReturn = Optional[Dict[str, Any]]

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
                amount, metadata) and returns a dict with optional fields:
                - category: str - single category account
                - payee: str - override transaction payee
                - narration: str - override transaction narration
                - subaccount: str - subaccount suffix
                - postings: List[Dict] - for splits, each with 'category' and 'amount'
                - receipts: List[str] - list of paths to receipt files
                Returns None for no categorization
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
            txn, documents = self._create_transaction_entry(transaction, filepath)
            if txn:
                entries.append(txn)
                # Add any associated document entries (receipts)
                entries.extend(documents)

        return entries

    def _create_transaction_entry(
        self, transaction: BancoChileTransaction, filepath: Path
    ) -> Tuple[Optional[data.Transaction], List[data.Document]]:
        """
        Create a Beancount transaction from a Banco de Chile transaction.

        Args:
            transaction: Banco de Chile transaction
            filepath: Source file path

        Returns:
            Tuple of (transaction entry, list of Document entries for receipts)
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
            return None, []

        # Extract payee and narration (defaults)
        payee = normalize_payee(transaction.description)
        narration = clean_narration(transaction.description)

        # Add channel information to metadata
        meta = data.new_metadata(str(filepath), 0)
        meta["channel"] = transaction.channel

        # Prepare metadata for categorizer
        categorizer_metadata = {
            "channel": transaction.channel,
            "debit": transaction.debit,
            "credit": transaction.credit,
            "balance": transaction.balance,
        }

        # Call categorizer if provided
        categorizer_result = None
        if self.categorizer:
            categorizer_result = self.categorizer(
                transaction.date.date(),
                payee,
                narration,
                txn_amount,
                categorizer_metadata,
            )

        # Extract overrides from categorizer result
        subaccount_suffix = None
        category_account = None
        split_postings = None
        receipt_paths: List[str] = []

        if categorizer_result:
            # Override payee if provided
            if "payee" in categorizer_result:
                payee = categorizer_result["payee"]

            # Override narration if provided
            if "narration" in categorizer_result:
                narration = categorizer_result["narration"]

            # Get subaccount suffix if provided
            if "subaccount" in categorizer_result:
                subaccount_suffix = categorizer_result["subaccount"]

            # Get category or postings
            if "postings" in categorizer_result:
                split_postings = categorizer_result["postings"]
            elif "category" in categorizer_result:
                category_account = categorizer_result["category"]

            # Get receipt paths if provided
            if "receipts" in categorizer_result:
                receipt_paths = categorizer_result["receipts"] or []

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

        # Add categorization postings
        if split_postings:
            # Multiple split postings
            for posting_dict in split_postings:
                postings.append(
                    data.Posting(
                        account=posting_dict["category"],
                        units=amount.Amount(posting_dict["amount"], self.currency),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    )
                )
        elif category_account:
            # Single category account
            postings.append(
                data.Posting(
                    account=category_account,
                    units=amount.Amount(-txn_amount, self.currency),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                )
            )

        # Generate a deterministic link if there are receipts
        txn_links: frozenset[str] = frozenset()
        if receipt_paths:
            # Create a deterministic link ID based on date, payee, and receipt paths
            # This ensures the same receipts always generate the same link
            date_str = transaction.date.date().isoformat()
            paths_str = ",".join(sorted(receipt_paths))
            hash_input = f"{date_str}:{payee}:{paths_str}"
            link_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
            link_id = f"rcpt-{link_hash}"
            txn_links = frozenset([link_id])

        # Create transaction
        txn = data.Transaction(
            meta=meta,
            date=transaction.date.date(),
            flag=flags.FLAG_OKAY,
            payee=payee,
            narration=narration,
            tags=frozenset(),
            links=txn_links,
            postings=postings,
        )

        # Create Document entries for receipts
        documents: List[data.Document] = []
        for receipt_path in receipt_paths:
            doc = data.Document(
                meta=data.new_metadata(str(filepath), 0),
                date=transaction.date.date(),
                account=account_name,
                filename=receipt_path,
                tags=None,
                links=txn_links if txn_links else None,
            )
            documents.append(doc)

        return txn, documents
