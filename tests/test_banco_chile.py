"""Tests for Banco de Chile importer."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from beancount_chile.banco_chile import BancoChileImporter
from beancount_chile.extractors.banco_chile_xls import BancoChileXLSExtractor

# Path to test fixture
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "banco_chile_cartola_sample.xls"


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
