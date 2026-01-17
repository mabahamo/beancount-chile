"""Tests for Banco de Chile credit card importer."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from beancount_chile.banco_chile_credit import BancoChileCreditImporter
from beancount_chile.extractors.banco_chile_credit_xls import (
    BancoChileCreditXLSExtractor,
    StatementType,
)

# Path to test fixtures
FIXTURE_FACTURADO = (
    Path(__file__).parent / "fixtures" / "banco_chile_credit_facturado_sample.xls"
)
FIXTURE_NO_FACTURADO = (
    Path(__file__).parent / "fixtures" / "banco_chile_credit_no_facturado_sample.xls"
)


class TestBancoChileCreditXLSExtractor:
    """Test the credit card XLS extractor."""

    def test_detect_facturado_type(self):
        """Test detection of billed statement type."""
        extractor = BancoChileCreditXLSExtractor()
        metadata, _ = extractor.extract(str(FIXTURE_FACTURADO))

        assert metadata.statement_type == StatementType.FACTURADO

    def test_detect_no_facturado_type(self):
        """Test detection of unbilled statement type."""
        extractor = BancoChileCreditXLSExtractor()
        metadata, _ = extractor.extract(str(FIXTURE_NO_FACTURADO))

        assert metadata.statement_type == StatementType.NO_FACTURADO

    def test_extract_facturado_metadata(self):
        """Test metadata extraction from billed statement."""
        extractor = BancoChileCreditXLSExtractor()
        metadata, _ = extractor.extract(str(FIXTURE_FACTURADO))

        assert metadata.account_holder == "Juan Pérez González"
        assert metadata.rut == "12.345.678-9"
        assert "Visa Infinite" in metadata.card_type
        assert metadata.card_last_four == "1234"
        assert metadata.card_status == "Vigente o Activo"
        assert metadata.statement_type == StatementType.FACTURADO
        assert isinstance(metadata.statement_date, datetime)

        # Facturado-specific fields
        assert isinstance(metadata.total_billed, Decimal)
        assert metadata.total_billed > 0
        assert isinstance(metadata.minimum_payment, Decimal)
        assert isinstance(metadata.billing_date, datetime)
        assert isinstance(metadata.due_date, datetime)

        # No Facturado fields should be None
        assert metadata.available_credit is None
        assert metadata.used_credit is None
        assert metadata.total_credit_limit is None

    def test_extract_no_facturado_metadata(self):
        """Test metadata extraction from unbilled statement."""
        extractor = BancoChileCreditXLSExtractor()
        metadata, _ = extractor.extract(str(FIXTURE_NO_FACTURADO))

        assert metadata.account_holder == "Juan Pérez González"
        assert metadata.rut == "12.345.678-9"
        assert "Visa Infinite" in metadata.card_type
        assert metadata.card_last_four == "1234"
        assert metadata.card_status == "Vigente o Activo"
        assert metadata.statement_type == StatementType.NO_FACTURADO
        assert isinstance(metadata.statement_date, datetime)

        # No Facturado-specific fields
        assert isinstance(metadata.available_credit, Decimal)
        assert metadata.available_credit > 0
        assert isinstance(metadata.used_credit, Decimal)
        assert isinstance(metadata.total_credit_limit, Decimal)

        # Facturado fields should be None
        assert metadata.total_billed is None
        assert metadata.minimum_payment is None
        assert metadata.billing_date is None
        assert metadata.due_date is None

    def test_extract_facturado_transactions(self):
        """Test transaction extraction from billed statement."""
        extractor = BancoChileCreditXLSExtractor()
        _, transactions = extractor.extract(str(FIXTURE_FACTURADO))

        assert len(transactions) > 0

        # Check first transaction structure
        first_txn = transactions[0]
        assert isinstance(first_txn.date, datetime)
        assert isinstance(first_txn.description, str)
        assert isinstance(first_txn.amount, Decimal)
        assert first_txn.amount > 0

        # Facturado-specific fields
        assert first_txn.category is not None
        assert first_txn.installments is not None

        # No Facturado fields should be None
        assert first_txn.card_type is None
        assert first_txn.city is None

    def test_extract_no_facturado_transactions(self):
        """Test transaction extraction from unbilled statement."""
        extractor = BancoChileCreditXLSExtractor()
        _, transactions = extractor.extract(str(FIXTURE_NO_FACTURADO))

        assert len(transactions) > 0

        # Check first transaction structure
        first_txn = transactions[0]
        assert isinstance(first_txn.date, datetime)
        assert isinstance(first_txn.description, str)
        assert isinstance(first_txn.amount, Decimal)
        assert first_txn.amount > 0

        # No Facturado-specific fields
        assert first_txn.card_type is not None
        assert first_txn.installments is not None

        # Facturado fields should be None
        assert first_txn.category is None

    def test_invalid_file(self):
        """Test handling of invalid files."""
        extractor = BancoChileCreditXLSExtractor()

        with pytest.raises(Exception):
            extractor.extract("nonexistent_file.xls")


class TestBancoChileCreditImporter:
    """Test the Banco de Chile credit card importer."""

    def test_identify_facturado_file(self):
        """Test file identification with billed statement."""
        importer = BancoChileCreditImporter(
            card_last_four="1234",
            account_name="Liabilities:CreditCard:BancoChile",
        )

        assert importer.identify(FIXTURE_FACTURADO) is True

    def test_identify_no_facturado_file(self):
        """Test file identification with unbilled statement."""
        importer = BancoChileCreditImporter(
            card_last_four="1234",
            account_name="Liabilities:CreditCard:BancoChile",
        )

        assert importer.identify(FIXTURE_NO_FACTURADO) is True

    def test_identify_wrong_card(self):
        """Test file identification with wrong card number."""
        importer = BancoChileCreditImporter(
            card_last_four="9999",
            account_name="Liabilities:CreditCard:BancoChile",
        )

        assert importer.identify(FIXTURE_FACTURADO) is False
        assert importer.identify(FIXTURE_NO_FACTURADO) is False

    def test_identify_wrong_extension(self):
        """Test file identification with wrong extension."""
        importer = BancoChileCreditImporter(
            card_last_four="1234",
            account_name="Liabilities:CreditCard:BancoChile",
        )

        fake_path = Path("test.pdf")
        assert importer.identify(fake_path) is False

    def test_account_name(self):
        """Test account name retrieval."""
        account_name = "Liabilities:CreditCard:BancoChile"
        importer = BancoChileCreditImporter(
            card_last_four="1234",
            account_name=account_name,
        )

        assert importer.account(FIXTURE_FACTURADO) == account_name
        assert importer.account(FIXTURE_NO_FACTURADO) == account_name

    def test_date_extraction(self):
        """Test date extraction."""
        importer = BancoChileCreditImporter(
            card_last_four="1234",
            account_name="Liabilities:CreditCard:BancoChile",
        )

        date_facturado = importer.date(FIXTURE_FACTURADO)
        assert date_facturado is not None
        assert isinstance(date_facturado, datetime)

        date_no_facturado = importer.date(FIXTURE_NO_FACTURADO)
        assert date_no_facturado is not None
        assert isinstance(date_no_facturado, datetime)

    def test_filename_generation_facturado(self):
        """Test filename generation for billed statement."""
        importer = BancoChileCreditImporter(
            card_last_four="1234",
            account_name="Liabilities:CreditCard:BancoChile",
        )

        filename = importer.filename(FIXTURE_FACTURADO)
        assert filename is not None
        assert "banco_chile_credit" in filename
        assert "1234" in filename
        assert "facturado" in filename
        assert filename.endswith(".xls")

    def test_filename_generation_no_facturado(self):
        """Test filename generation for unbilled statement."""
        importer = BancoChileCreditImporter(
            card_last_four="1234",
            account_name="Liabilities:CreditCard:BancoChile",
        )

        filename = importer.filename(FIXTURE_NO_FACTURADO)
        assert filename is not None
        assert "banco_chile_credit" in filename
        assert "1234" in filename
        assert "no_facturado" in filename
        assert filename.endswith(".xls")

    def test_extract_facturado_entries(self):
        """Test entry extraction from billed statement."""
        importer = BancoChileCreditImporter(
            card_last_four="1234",
            account_name="Liabilities:CreditCard:BancoChile",
        )

        entries = importer.extract(FIXTURE_FACTURADO)

        # Should have note + transactions
        assert len(entries) > 1

        # Check for note entry
        note_entries = [e for e in entries if e.__class__.__name__ == "Note"]
        assert len(note_entries) == 1
        note = note_entries[0]
        assert "FACTURADO" in note.comment
        assert note.account == "Liabilities:CreditCard:BancoChile"

        # Check for transactions
        txn_entries = [e for e in entries if e.__class__.__name__ == "Transaction"]
        assert len(txn_entries) > 0

        # Verify transaction structure
        for txn in txn_entries:
            assert txn.date is not None
            assert len(txn.postings) == 1
            assert txn.postings[0].account == "Liabilities:CreditCard:BancoChile"
            assert txn.postings[0].units.currency == "CLP"
            assert txn.postings[0].units.number > 0  # Credit card charges are positive
            # Billed transactions should be cleared (*)
            assert txn.flag == "*"
            # Should have statement_type metadata
            assert "statement_type" in txn.meta
            assert txn.meta["statement_type"] == "facturado"

    def test_extract_no_facturado_entries(self):
        """Test entry extraction from unbilled statement."""
        importer = BancoChileCreditImporter(
            card_last_four="1234",
            account_name="Liabilities:CreditCard:BancoChile",
        )

        entries = importer.extract(FIXTURE_NO_FACTURADO)

        # Should have note + transactions
        assert len(entries) > 1

        # Check for note entry
        note_entries = [e for e in entries if e.__class__.__name__ == "Note"]
        assert len(note_entries) == 1
        note = note_entries[0]
        assert "NO FACTURADO" in note.comment
        assert note.account == "Liabilities:CreditCard:BancoChile"

        # Check for transactions
        txn_entries = [e for e in entries if e.__class__.__name__ == "Transaction"]
        assert len(txn_entries) > 0

        # Verify transaction structure
        for txn in txn_entries:
            assert txn.date is not None
            assert len(txn.postings) == 1
            assert txn.postings[0].account == "Liabilities:CreditCard:BancoChile"
            assert txn.postings[0].units.currency == "CLP"
            assert txn.postings[0].units.number > 0  # Credit card charges are positive
            # Unbilled transactions should be pending (!)
            assert txn.flag == "!"
            # Should have statement_type metadata
            assert "statement_type" in txn.meta
            assert txn.meta["statement_type"] == "no_facturado"

    def test_extract_with_custom_currency(self):
        """Test extraction with custom currency."""
        importer = BancoChileCreditImporter(
            card_last_four="1234",
            account_name="Liabilities:CreditCard:BancoChile",
            currency="CLP",
        )

        entries = importer.extract(FIXTURE_FACTURADO)
        txn_entries = [e for e in entries if e.__class__.__name__ == "Transaction"]

        for txn in txn_entries:
            assert txn.postings[0].units.currency == "CLP"

    def test_metadata_preservation(self):
        """Test that metadata is preserved in transactions."""
        importer = BancoChileCreditImporter(
            card_last_four="1234",
            account_name="Liabilities:CreditCard:BancoChile",
        )

        # Test facturado
        entries_facturado = importer.extract(FIXTURE_FACTURADO)
        txn_facturado = [
            e for e in entries_facturado if e.__class__.__name__ == "Transaction"
        ][0]
        assert "category" in txn_facturado.meta
        assert "installments" in txn_facturado.meta

        # Test no facturado
        entries_no_facturado = importer.extract(FIXTURE_NO_FACTURADO)
        txn_no_facturado = [
            e for e in entries_no_facturado if e.__class__.__name__ == "Transaction"
        ][0]
        assert "installments" in txn_no_facturado.meta
        # City may or may not be present depending on transaction
