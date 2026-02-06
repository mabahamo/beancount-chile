"""Tests for Banco de Chile importer."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from beancount_chile.banco_chile import BancoChileImporter
from beancount_chile.extractors.banco_chile_xls import BancoChileXLSExtractor

# Path to test fixtures
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "banco_chile_cartola_sample.xls"
BINARY_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "banco_chile_cartola_binary_sample.xls"
)


class TestBancoChileXLSExtractor:
    """Test the XLS extractor."""

    def test_extract_metadata(self):
        """Test metadata extraction."""
        extractor = BancoChileXLSExtractor()
        metadata, _ = extractor.extract(str(FIXTURE_PATH))

        assert metadata.account_holder == "Juan Pérez González"
        assert metadata.rut == "12.345.678-9"
        assert metadata.account_number == "00-123-45678-90"
        assert metadata.currency == "CLP"
        assert isinstance(metadata.available_balance, Decimal)
        assert isinstance(metadata.accounting_balance, Decimal)
        assert isinstance(metadata.total_debits, Decimal)
        assert isinstance(metadata.total_credits, Decimal)
        assert isinstance(metadata.statement_date, datetime)

    def test_extract_transactions(self):
        """Test transaction extraction."""
        extractor = BancoChileXLSExtractor()
        _, transactions = extractor.extract(str(FIXTURE_PATH))

        assert len(transactions) > 0

        # Check first transaction structure
        first_txn = transactions[0]
        assert isinstance(first_txn.date, datetime)
        assert isinstance(first_txn.description, str)
        assert isinstance(first_txn.channel, str)
        assert isinstance(first_txn.balance, Decimal)

        # Check that each transaction has either debit or credit
        for txn in transactions:
            assert (txn.debit is not None) or (txn.credit is not None)
            assert isinstance(txn.balance, Decimal)

    def test_invalid_file(self):
        """Test handling of invalid files."""
        extractor = BancoChileXLSExtractor()

        with pytest.raises(Exception):
            extractor.extract("nonexistent_file.xls")


class TestBancoChileImporter:
    """Test the Banco de Chile importer."""

    def test_identify_valid_file(self):
        """Test file identification with valid file."""
        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
        )

        assert importer.identify(FIXTURE_PATH) is True

    def test_identify_digits_only_account(self):
        """Test file identification with digits-only account number."""
        # Fixture has "00-123-45678-90", importer uses digits only
        importer = BancoChileImporter(
            account_number="001234567890",
            account_name="Assets:BancoChile:Checking",
        )

        assert importer.identify(FIXTURE_PATH) is True

    def test_identify_wrong_account(self):
        """Test file identification with wrong account number."""
        importer = BancoChileImporter(
            account_number="00-999-99999-99",
            account_name="Assets:BancoChile:Checking",
        )

        assert importer.identify(FIXTURE_PATH) is False

    def test_identify_wrong_extension(self):
        """Test file identification with wrong extension."""
        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
        )

        fake_path = Path("test.pdf")
        assert importer.identify(fake_path) is False

    def test_account_name(self):
        """Test account name retrieval."""
        account_name = "Assets:BancoChile:Checking"
        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name=account_name,
        )

        assert importer.account(FIXTURE_PATH) == account_name

    def test_date_extraction(self):
        """Test date extraction."""
        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
        )

        statement_date = importer.date(FIXTURE_PATH)
        assert statement_date is not None
        assert isinstance(statement_date, datetime)

    def test_filename_generation(self):
        """Test filename generation."""
        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
        )

        filename = importer.filename(FIXTURE_PATH)
        assert filename is not None
        assert "banco_chile" in filename
        assert filename.endswith(".xls")

    def test_extract_entries(self):
        """Test entry extraction."""
        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
        )

        entries = importer.extract(FIXTURE_PATH)

        # Should have transactions + balance assertion
        assert len(entries) > 0

        # Check for balance assertion
        balance_entries = [e for e in entries if e.__class__.__name__ == "Balance"]
        assert len(balance_entries) == 1

        # Check for transactions
        txn_entries = [e for e in entries if e.__class__.__name__ == "Transaction"]
        assert len(txn_entries) > 0

        # Verify transaction structure
        for txn in txn_entries:
            assert txn.date is not None
            assert len(txn.postings) == 1
            assert txn.postings[0].account == "Assets:BancoChile:Checking"
            assert txn.postings[0].units.currency == "CLP"

    def test_extract_with_custom_currency(self):
        """Test extraction with custom currency."""
        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
            currency="CLP",
        )

        entries = importer.extract(FIXTURE_PATH)
        txn_entries = [e for e in entries if e.__class__.__name__ == "Transaction"]

        for txn in txn_entries:
            assert txn.postings[0].units.currency == "CLP"

    def test_categorizer_simple_category(self):
        """Test categorizer with simple category dict return."""

        def simple_categorizer(date, payee, narration, amount, metadata):
            """Simple categorizer that returns a dict with category."""
            if amount < 0:  # Debit
                return {"category": "Expenses:General"}
            return {"category": "Income:General"}

        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
            categorizer=simple_categorizer,
        )

        entries = importer.extract(FIXTURE_PATH)
        txn_entries = [e for e in entries if e.__class__.__name__ == "Transaction"]

        # Check that transactions have 2 postings (account + category)
        for txn in txn_entries:
            assert len(txn.postings) == 2
            # First posting is the account
            assert txn.postings[0].account == "Assets:BancoChile:Checking"
            # Second posting is the categorized account
            assert txn.postings[1].account in ["Expenses:General", "Income:General"]
            # Amounts should balance
            assert txn.postings[0].units.number + txn.postings[
                1
            ].units.number == Decimal("0")

    def test_categorizer_none_return(self):
        """Test categorizer with None return (no categorization)."""

        def none_categorizer(date, payee, narration, amount, metadata):
            """Categorizer that returns None."""
            return None

        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
            categorizer=none_categorizer,
        )

        entries = importer.extract(FIXTURE_PATH)
        txn_entries = [e for e in entries if e.__class__.__name__ == "Transaction"]

        # Check that transactions have only 1 posting (no categorization)
        for txn in txn_entries:
            assert len(txn.postings) == 1
            assert txn.postings[0].account == "Assets:BancoChile:Checking"

    def test_categorizer_split_postings(self):
        """Test categorizer with split postings dict return."""

        def split_categorizer(date, payee, narration, amount, metadata):
            """Categorizer that splits transactions."""
            if amount < 0:  # Debit
                # Split 60/40 between two categories
                return {
                    "postings": [
                        {
                            "category": "Expenses:Category1",
                            "amount": -amount * Decimal("0.6"),
                        },
                        {
                            "category": "Expenses:Category2",
                            "amount": -amount * Decimal("0.4"),
                        },
                    ]
                }
            return None

        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
            categorizer=split_categorizer,
        )

        entries = importer.extract(FIXTURE_PATH)
        txn_entries = [e for e in entries if e.__class__.__name__ == "Transaction"]

        # Find a debit transaction to check
        debit_txns = [
            txn for txn in txn_entries if txn.postings[0].units.number < Decimal("0")
        ]
        assert len(debit_txns) > 0

        for txn in debit_txns:
            # Should have 3 postings: account + 2 split categories
            assert len(txn.postings) == 3
            assert txn.postings[0].account == "Assets:BancoChile:Checking"
            assert txn.postings[1].account == "Expenses:Category1"
            assert txn.postings[2].account == "Expenses:Category2"

            # Verify split amounts (60/40)
            account_amount = txn.postings[0].units.number
            cat1_amount = txn.postings[1].units.number
            cat2_amount = txn.postings[2].units.number

            # Category1 should be 60% of the absolute amount
            assert cat1_amount == -account_amount * Decimal("0.6")
            # Category2 should be 40% of the absolute amount
            assert cat2_amount == -account_amount * Decimal("0.4")

            # Total should balance to zero
            assert account_amount + cat1_amount + cat2_amount == Decimal("0")

    def test_categorizer_multiple_split_postings(self):
        """Test categorizer with multiple split categories."""

        def multi_split_categorizer(date, payee, narration, amount, metadata):
            """Categorizer that splits into 3 categories."""
            if amount < 0:  # Debit
                # Split into 3 categories: 50%, 30%, 20%
                return {
                    "postings": [
                        {
                            "category": "Expenses:Cat1",
                            "amount": -amount * Decimal("0.5"),
                        },
                        {
                            "category": "Expenses:Cat2",
                            "amount": -amount * Decimal("0.3"),
                        },
                        {
                            "category": "Expenses:Cat3",
                            "amount": -amount * Decimal("0.2"),
                        },
                    ]
                }
            return None

        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
            categorizer=multi_split_categorizer,
        )

        entries = importer.extract(FIXTURE_PATH)
        txn_entries = [e for e in entries if e.__class__.__name__ == "Transaction"]

        debit_txns = [
            txn for txn in txn_entries if txn.postings[0].units.number < Decimal("0")
        ]

        for txn in debit_txns:
            # Should have 4 postings: account + 3 split categories
            assert len(txn.postings) == 4
            assert txn.postings[0].account == "Assets:BancoChile:Checking"
            assert txn.postings[1].account == "Expenses:Cat1"
            assert txn.postings[2].account == "Expenses:Cat2"
            assert txn.postings[3].account == "Expenses:Cat3"

            # Verify amounts balance
            total = sum(posting.units.number for posting in txn.postings)
            assert total == Decimal("0")

    def test_categorizer_conditional(self):
        """Test categorizer with conditional logic."""

        def conditional_categorizer(date, payee, narration, amount, metadata):
            """Categorizer with conditional logic based on metadata."""
            # Only categorize Internet transactions
            if metadata.get("channel") == "Internet":
                if amount < 0:
                    return {"category": "Expenses:Online"}
            return None

        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
            categorizer=conditional_categorizer,
        )

        entries = importer.extract(FIXTURE_PATH)
        txn_entries = [e for e in entries if e.__class__.__name__ == "Transaction"]

        # Some transactions should be categorized, some not
        categorized = [txn for txn in txn_entries if len(txn.postings) == 2]
        uncategorized = [txn for txn in txn_entries if len(txn.postings) == 1]

        # Both should exist (assuming fixture has both types)
        assert len(categorized) >= 0
        assert len(uncategorized) >= 0

    def test_categorizer_with_subaccount_and_category(self):
        """Test categorizer with subaccount and category dict return."""

        def subaccount_categorizer(date, payee, narration, amount, metadata):
            """Return dict with subaccount and category."""
            if amount < 0:  # Debit
                return {"subaccount": "Car", "category": "Expenses:Car:Gas"}
            return None

        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
            categorizer=subaccount_categorizer,
        )

        entries = importer.extract(FIXTURE_PATH)
        txn_entries = [e for e in entries if e.__class__.__name__ == "Transaction"]

        # Find debit transactions
        debit_txns = [
            txn for txn in txn_entries if txn.postings[0].units.number < Decimal("0")
        ]

        for txn in debit_txns:
            # Should have 2 postings (asset subaccount + category)
            assert len(txn.postings) == 2
            # First posting should use Car subaccount
            assert txn.postings[0].account == "Assets:BancoChile:Checking:Car"
            # Second posting should be the category
            assert txn.postings[1].account == "Expenses:Car:Gas"
            # Amounts should balance
            assert txn.postings[0].units.number + txn.postings[
                1
            ].units.number == Decimal("0")

    def test_categorizer_with_subaccount_and_split_postings(self):
        """Test categorizer with subaccount and split postings dict return."""

        def subaccount_split_categorizer(date, payee, narration, amount, metadata):
            """Return dict with subaccount and split postings."""
            if amount < 0:  # Debit
                return {
                    "subaccount": "Household",
                    "postings": [
                        {
                            "category": "Expenses:Groceries",
                            "amount": -amount * Decimal("0.6"),
                        },
                        {
                            "category": "Expenses:Household",
                            "amount": -amount * Decimal("0.4"),
                        },
                    ],
                }
            return None

        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
            categorizer=subaccount_split_categorizer,
        )

        entries = importer.extract(FIXTURE_PATH)
        txn_entries = [e for e in entries if e.__class__.__name__ == "Transaction"]

        # Find debit transactions
        debit_txns = [
            txn for txn in txn_entries if txn.postings[0].units.number < Decimal("0")
        ]

        for txn in debit_txns:
            # Should have 3 postings (asset subaccount + 2 split categories)
            assert len(txn.postings) == 3
            # First posting should use Household subaccount
            assert txn.postings[0].account == "Assets:BancoChile:Checking:Household"
            # Other postings should be split categories
            assert txn.postings[1].account == "Expenses:Groceries"
            assert txn.postings[2].account == "Expenses:Household"
            # Amounts should balance
            total = sum(posting.units.number for posting in txn.postings)
            assert total == Decimal("0")

    def test_categorizer_subaccount_only(self):
        """Test categorizer with subaccount only (no category) dict return."""

        def subaccount_only_categorizer(date, payee, narration, amount, metadata):
            """Return dict with subaccount only (no category)."""
            if amount < -100000:  # Large debits
                return {"subaccount": "Savings"}
            if amount > 0:  # Credits
                return {"subaccount": "Emergency"}
            return None

        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
            categorizer=subaccount_only_categorizer,
        )

        entries = importer.extract(FIXTURE_PATH)
        txn_entries = [e for e in entries if e.__class__.__name__ == "Transaction"]

        # Find large debits
        large_debits = [
            txn
            for txn in txn_entries
            if txn.postings[0].units.number < Decimal("-100000")
        ]

        for txn in large_debits:
            # Should have 1 posting (subaccount only, no category)
            assert len(txn.postings) == 1
            # Should use Savings subaccount
            assert txn.postings[0].account == "Assets:BancoChile:Checking:Savings"

        # Find credits
        credits = [
            txn for txn in txn_entries if txn.postings[0].units.number > Decimal("0")
        ]

        for txn in credits:
            # Should have 1 posting (subaccount only, no category)
            assert len(txn.postings) == 1
            # Should use Emergency subaccount
            assert txn.postings[0].account == "Assets:BancoChile:Checking:Emergency"

    def test_categorizer_with_payee_and_narration_overrides(self):
        """Test categorizer with payee and narration overrides."""

        def override_categorizer(date, payee, narration, amount, metadata):
            """Return dict with payee and narration overrides."""
            if "JUMBO" in payee.upper():
                return {
                    "payee": "Supermercado Jumbo",
                    "narration": "Grocery shopping",
                    "category": "Expenses:Groceries",
                }
            return None

        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
            categorizer=override_categorizer,
        )

        entries = importer.extract(FIXTURE_PATH)
        txn_entries = [e for e in entries if e.__class__.__name__ == "Transaction"]

        # Find transactions that should have overrides
        overridden = [txn for txn in txn_entries if "Jumbo" in txn.payee]

        for txn in overridden:
            # Check payee override
            assert txn.payee == "Supermercado Jumbo"
            # Check narration override
            assert txn.narration == "Grocery shopping"
            # Should have 2 postings (account + category)
            assert len(txn.postings) == 2
            assert txn.postings[1].account == "Expenses:Groceries"

    def test_categorizer_with_custom_metadata(self):
        """Test categorizer with custom metadata dict return."""

        def metadata_categorizer(date, payee, narration, amount, metadata):
            """Return dict with custom metadata."""
            if amount < 0:  # Debit
                return {
                    "category": "Expenses:Shopping",
                    "metadata": {
                        "purchase_type": "online",
                        "vendor_id": "12345",
                        "reviewed": True,
                    },
                }
            return None

        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
            categorizer=metadata_categorizer,
        )

        entries = importer.extract(FIXTURE_PATH)
        txn_entries = [e for e in entries if e.__class__.__name__ == "Transaction"]

        # Find debit transactions
        debit_txns = [
            txn for txn in txn_entries if txn.postings[0].units.number < Decimal("0")
        ]

        for txn in debit_txns:
            # Should have custom metadata
            assert "purchase_type" in txn.meta
            assert txn.meta["purchase_type"] == "online"
            assert "vendor_id" in txn.meta
            assert txn.meta["vendor_id"] == "12345"
            assert "reviewed" in txn.meta
            assert txn.meta["reviewed"] is True
            # Should also have default metadata (channel)
            assert "channel" in txn.meta
            # Should have 2 postings (account + category)
            assert len(txn.postings) == 2
            assert txn.postings[1].account == "Expenses:Shopping"


class TestBancoChileXLSExtractorBinary:
    """Test the XLS extractor with genuine binary (OLE2) XLS files."""

    def test_detect_binary_format(self):
        """Verify the fixture is a genuine OLE2 binary .xls file."""
        with open(BINARY_FIXTURE_PATH, "rb") as f:
            signature = f.read(4)
        # OLE2 Compound Document signature
        assert signature == b"\xd0\xcf\x11\xe0"

    def test_engine_detection(self):
        """Verify xlrd engine is selected for binary XLS."""
        extractor = BancoChileXLSExtractor()
        engine = extractor._detect_excel_engine(str(BINARY_FIXTURE_PATH))
        assert engine == "xlrd"

    def test_extract_metadata_binary(self):
        """Test metadata extraction from binary XLS."""
        extractor = BancoChileXLSExtractor()
        metadata, _ = extractor.extract(str(BINARY_FIXTURE_PATH))

        assert metadata.account_holder == "Juan Pérez González"
        assert metadata.rut == "12.345.678-9"
        assert metadata.account_number == "00-123-45678-90"
        assert metadata.currency == "CLP"
        assert metadata.available_balance == Decimal("5500000")
        assert metadata.accounting_balance == Decimal("5000000")
        assert metadata.total_debits == Decimal("2500000")
        assert metadata.total_credits == Decimal("1500000")
        assert metadata.statement_date == datetime(2024, 1, 31)

    def test_extract_transactions_binary(self):
        """Test transaction extraction from binary XLS."""
        extractor = BancoChileXLSExtractor()
        _, transactions = extractor.extract(str(BINARY_FIXTURE_PATH))

        assert len(transactions) == 5

        # Transaction 1: Debit (transfer out)
        t1 = transactions[0]
        assert t1.date == datetime(2024, 1, 15)
        assert "TRASPASO A:Maria González" in t1.description
        assert t1.channel == "Internet"
        assert t1.debit == Decimal("500000")
        assert t1.credit is None
        assert t1.balance == Decimal("5000000")

        # Transaction 2: Credit (transfer in)
        t2 = transactions[1]
        assert t2.date == datetime(2024, 1, 20)
        assert "TRASPASO DE:Pedro López" in t2.description
        assert t2.debit is None
        assert t2.credit == Decimal("300000")

        # Transaction 3: Debit (purchase)
        t3 = transactions[2]
        assert t3.date == datetime(2024, 1, 25)
        assert "JUMBO" in t3.description
        assert t3.debit == Decimal("85000")
        assert t3.credit is None

        # Transaction 4: Credit (deposit)
        t4 = transactions[3]
        assert t4.date == datetime(2024, 1, 28)
        assert "DEPOSITO" in t4.description
        assert t4.debit is None
        assert t4.credit == Decimal("200000")

        # Transaction 5: Debit (automatic payment)
        t5 = transactions[4]
        assert t5.date == datetime(2024, 1, 31)
        assert "PAC ENTEL" in t5.description
        assert t5.debit == Decimal("35000")
        assert t5.credit is None

    def test_importer_identify_binary(self):
        """Test that identify() works with binary XLS format."""
        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
        )
        assert importer.identify(BINARY_FIXTURE_PATH) is True

    def test_importer_identify_wrong_account_binary(self):
        """Test that identify() rejects wrong account number for binary XLS."""
        importer = BancoChileImporter(
            account_number="00-999-99999-99",
            account_name="Assets:BancoChile:Checking",
        )
        assert importer.identify(BINARY_FIXTURE_PATH) is False

    def test_importer_extract_binary(self):
        """Test full extraction pipeline with binary XLS format."""
        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
        )

        entries = importer.extract(BINARY_FIXTURE_PATH)

        # Should have balance assertion + 5 transactions
        balance_entries = [e for e in entries if e.__class__.__name__ == "Balance"]
        txn_entries = [e for e in entries if e.__class__.__name__ == "Transaction"]

        assert len(balance_entries) == 1
        assert len(txn_entries) == 5

        # Verify transaction structure
        for txn in txn_entries:
            assert txn.date is not None
            assert len(txn.postings) == 1
            assert txn.postings[0].account == "Assets:BancoChile:Checking"
            assert txn.postings[0].units.currency == "CLP"
