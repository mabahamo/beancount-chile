"""Beancount importer for Banco de Chile credit card statements."""

import hashlib
from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from beancount.core import amount, data, flags
from beancount.core.number import D
from beangulp import Importer

from beancount_chile.extractors.banco_chile_credit_xls import (
    BancoChileCreditTransaction,
    BancoChileCreditXLSExtractor,
    StatementType,
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


class BancoChileCreditImporter(Importer):
    """Importer for Banco de Chile credit card XLS/XLSX statements."""

    def __init__(
        self,
        card_last_four: str,
        account_name: str,
        currency: str = "CLP",
        file_encoding: str = "utf-8",
        categorizer: Optional[CategorizerFunc] = None,
    ):
        """
        Initialize the Banco de Chile credit card importer.

        Args:
            card_last_four: Last 4 digits of the card (e.g., "1234")
            account_name: Beancount account name
                (e.g., "Liabilities:CreditCard:BancoChile")
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
        self.card_last_four = card_last_four
        self.account_name = account_name
        self.currency = currency
        self.file_encoding = file_encoding
        self.categorizer = categorizer
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
            txn, documents = self._create_transaction_entry(
                transaction, metadata, filepath
            )
            if txn:
                entries.append(txn)
                # Add any associated document entries (receipts)
                entries.extend(documents)

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
    ) -> Tuple[Optional[data.Transaction], List[data.Document]]:
        """
        Create a Beancount transaction from a credit card transaction.

        Args:
            transaction: Credit card transaction
            metadata: Statement metadata
            filepath: Source file path

        Returns:
            Tuple of (transaction entry, list of Document entries for receipts)
        """
        # Credit card charges are positive (increase liability)
        txn_amount = D(str(transaction.amount))

        # Extract payee and narration (defaults)
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

        # Prepare metadata for categorizer
        categorizer_metadata = {
            "statement_type": meta["statement_type"],
            "installments": transaction.installments,
            "category": transaction.category,
            "city": transaction.city,
            "card_type": transaction.card_type,
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
            flag=flag,
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
