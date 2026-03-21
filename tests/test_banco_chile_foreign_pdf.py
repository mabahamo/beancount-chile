"""Tests for Banco de Chile foreign currency PDF extractor."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from beancount_chile.banco_chile import BancoChileImporter
from beancount_chile.extractors.banco_chile_foreign_pdf import (
    BancoChileForeignPDFExtractor,
    detect_currency_from_header,
    extract_foreign_account_holder,
    parse_foreign_amount,
    parse_foreign_transaction_line,
)


class TestParseForeignAmount:
    """Test foreign currency amount parsing."""

    def test_simple_amount(self):
        assert parse_foreign_amount("100,00") == Decimal("100.00")

    def test_with_thousands(self):
        assert parse_foreign_amount("1.234,56") == Decimal("1234.56")

    def test_large_amount(self):
        assert parse_foreign_amount("79.371,00") == Decimal("79371.00")

    def test_small_amount(self):
        assert parse_foreign_amount("15,00") == Decimal("15.00")

    def test_negative(self):
        assert parse_foreign_amount("-100,00") == Decimal("-100.00")

    def test_zero(self):
        assert parse_foreign_amount("0,00") == Decimal("0.00")

    def test_empty_string(self):
        assert parse_foreign_amount("") == Decimal("0")
        assert parse_foreign_amount("   ") == Decimal("0")

    def test_with_spaces(self):
        assert parse_foreign_amount(" 1.234,56 ") == Decimal("1234.56")


class TestDetectCurrencyFromHeader:
    """Test currency detection from header."""

    def test_us_dollar(self):
        text = "MONEDA : US DOLLAR"
        assert detect_currency_from_header(text) == "USD"

    def test_us_dollar_no_colon(self):
        text = "MONEDA US DOLLAR"
        assert detect_currency_from_header(text) == "USD"

    def test_euro(self):
        text = "MONEDA : EURO"
        assert detect_currency_from_header(text) == "EUR"

    def test_no_moneda(self):
        text = "Some random text without currency"
        assert detect_currency_from_header(text) == "CLP"

    def test_in_full_header(self):
        text = """N° DE CUENTA : 59012345678
CARTOLA N° : 1
DESDE : 01/07/2025 HASTA : 01/07/2025
MONEDA : US DOLLAR"""
        assert detect_currency_from_header(text) == "USD"


class TestExtractForeignAccountHolder:
    """Test account holder extraction from foreign PDF format."""

    def test_extract_holder(self):
        text = "SR(A)(ES)\nJuan Perez Gonzalez\njuan@example.com"
        holder = extract_foreign_account_holder(text)
        assert holder == "Juan Perez Gonzalez"

    def test_extract_holder_with_accents(self):
        text = "SR(A)(ES)\nMaría González López\nmaria@example.com"
        holder = extract_foreign_account_holder(text)
        assert holder == "María González López"

    def test_no_match(self):
        text = "Some random text"
        holder = extract_foreign_account_holder(text)
        assert holder is None

    def test_with_extra_whitespace(self):
        text = "SR(A)(ES)\n  Juan Perez Gonzalez  \njuan@example.com"
        holder = extract_foreign_account_holder(text)
        assert holder == "Juan Perez Gonzalez"


class TestParseForeignTransactionLine:
    """Test foreign currency transaction line parsing."""

    def test_credit_with_document_number(self):
        """Test SRV CPRA USD as credit with document number."""
        line = "03/06 SRV CPRA USD BANCHILE N°12345678 INTERNET 100,00"
        txn = parse_foreign_transaction_line(line, 2025)

        assert txn is not None
        assert txn.date == datetime(2025, 6, 3)
        assert "SRV CPRA USD BANCHILE" in txn.description
        assert txn.channel == "INTERNET"
        assert txn.credit == Decimal("100.00")
        assert txn.debit is None
        assert txn.document_number == "12345678"

    def test_credit_with_balance(self):
        """Test SRV CPRA USD credit with balance."""
        line = "09/06 SRV CPRA USD BANCHILE N°98765432 INTERNET 100,00 180,00"
        txn = parse_foreign_transaction_line(line, 2025)

        assert txn is not None
        assert txn.credit == Decimal("100.00")
        assert txn.debit is None
        assert txn.balance == Decimal("180.00")
        assert txn.document_number == "98765432"

    def test_debit_with_balance(self):
        """Test TRANSFERENCIA DE FONDOS as debit."""
        line = "03/06 TRANSFERENCIA DE FONDOS INTERNET 20,00 80,00"
        txn = parse_foreign_transaction_line(line, 2025)

        assert txn is not None
        assert txn.date == datetime(2025, 6, 3)
        assert txn.description == "TRANSFERENCIA DE FONDOS"
        assert txn.channel == "INTERNET"
        assert txn.debit == Decimal("20.00")
        assert txn.credit is None
        assert txn.balance == Decimal("80.00")

    def test_debit_without_balance(self):
        """Test debit transaction with only one amount."""
        line = "18/06 TRANSFERENCIA DE FONDOS INTERNET 100,00"
        txn = parse_foreign_transaction_line(line, 2025)

        assert txn is not None
        assert txn.debit == Decimal("100.00")
        assert txn.credit is None
        assert txn.balance == Decimal("0")

    def test_skip_saldo_inicial(self):
        assert parse_foreign_transaction_line("01/07 SALDO INICIAL 0,00", 2025) is None

    def test_skip_saldo_final(self):
        assert parse_foreign_transaction_line("01/07 SALDO FINAL 80,00", 2025) is None

    def test_skip_total_cheques(self):
        assert (
            parse_foreign_transaction_line("TOTAL CHEQUES Y OTROS CARGOS 120,00", 2025)
            is None
        )

    def test_skip_total_depositos(self):
        assert (
            parse_foreign_transaction_line(
                "TOTAL DEPOSITOS Y OTROS ABONOS 200,00", 2025
            )
            is None
        )

    def test_skip_saldo_contable(self):
        assert (
            parse_foreign_transaction_line("SALDO CONTABLE ANTERIOR 0,00", 2025) is None
        )

    def test_empty_line(self):
        assert parse_foreign_transaction_line("", 2025) is None
        assert parse_foreign_transaction_line("   ", 2025) is None

    def test_no_document_number(self):
        """Test transaction without document number."""
        line = "03/06 TRANSFERENCIA DE FONDOS INTERNET 20,00 80,00"
        txn = parse_foreign_transaction_line(line, 2025)

        assert txn is not None
        assert txn.document_number is None


class TestBancoChileForeignPDFExtractor:
    """Test the foreign currency PDF extractor with mocked pdfplumber."""

    @patch("beancount_chile.extractors.banco_chile_foreign_pdf.pdfplumber.open")
    def test_extract_usd_pdf(self, mock_pdfplumber):
        """Test extraction of USD PDF statement."""
        page_text = """SR(A)(ES)
Juan Perez Gonzalez
juan@example.com

N° DE CUENTA : 59012345678
CARTOLA N° : 1
DESDE : 01/07/2025 HASTA : 01/07/2025
MONEDA : US DOLLAR

01/07 SALDO INICIAL 0,00
03/06 SRV CPRA USD BANCHILE N°12345678 INTERNET 100,00
03/06 TRANSFERENCIA DE FONDOS INTERNET 20,00 80,00
09/06 SRV CPRA USD BANCHILE N°87654321 INTERNET 100,00 180,00
18/06 TRANSFERENCIA DE FONDOS INTERNET 100,00
01/07 SALDO FINAL 80,00

TOTAL CHEQUES Y OTROS CARGOS 120,00
TOTAL DEPOSITOS Y OTROS ABONOS 200,00
SALDO CONTABLE ANTERIOR 0,00
SALDO CONTABLE ACTUAL 80,00"""

        mock_page = MagicMock()
        mock_page.extract_text.return_value = page_text

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__.return_value = mock_pdf
        mock_pdf.__exit__.return_value = None

        mock_pdfplumber.return_value = mock_pdf

        extractor = BancoChileForeignPDFExtractor()
        metadata, transactions = extractor.extract("fake.pdf")

        # Verify metadata
        assert metadata.account_number == "59012345678"
        assert metadata.account_holder == "Juan Perez Gonzalez"
        assert metadata.currency == "USD"
        assert metadata.rut == "N/A"
        assert metadata.statement_date == datetime(2025, 7, 1)
        assert metadata.accounting_balance == Decimal("80.00")

        # Verify transactions
        assert len(transactions) == 4

        # First: SRV CPRA USD credit
        assert transactions[0].credit == Decimal("100.00")
        assert transactions[0].debit is None
        assert transactions[0].document_number == "12345678"

        # Second: TRANSFERENCIA debit
        assert transactions[1].debit == Decimal("20.00")
        assert transactions[1].credit is None
        assert transactions[1].balance == Decimal("80.00")

        # Third: SRV CPRA USD credit
        assert transactions[2].credit == Decimal("100.00")
        assert transactions[2].document_number == "87654321"
        assert transactions[2].balance == Decimal("180.00")

        # Fourth: TRANSFERENCIA debit
        assert transactions[3].debit == Decimal("100.00")
        assert transactions[3].credit is None

    @patch("beancount_chile.extractors.banco_chile_foreign_pdf.pdfplumber.open")
    def test_extract_totals(self, mock_pdfplumber):
        """Test that total debits and credits are computed correctly."""
        page_text = """SR(A)(ES)
Juan Perez Gonzalez
juan@example.com

N° DE CUENTA : 59012345678
CARTOLA N° : 1
DESDE : 01/07/2025 HASTA : 01/07/2025
MONEDA : US DOLLAR

01/07 SALDO INICIAL 0,00
03/06 SRV CPRA USD BANCHILE N°12345678 INTERNET 100,00
03/06 TRANSFERENCIA DE FONDOS INTERNET 20,00 80,00
01/07 SALDO FINAL 80,00"""

        mock_page = MagicMock()
        mock_page.extract_text.return_value = page_text

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__.return_value = mock_pdf
        mock_pdf.__exit__.return_value = None

        mock_pdfplumber.return_value = mock_pdf

        extractor = BancoChileForeignPDFExtractor()
        metadata, _ = extractor.extract("fake.pdf")

        assert metadata.total_credits == Decimal("100.00")
        assert metadata.total_debits == Decimal("20.00")

    @patch("beancount_chile.extractors.banco_chile_foreign_pdf.pdfplumber.open")
    def test_extract_missing_account_number(self, mock_pdfplumber):
        """Test that extraction fails when account number is missing."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Some text without account info"

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__.return_value = mock_pdf
        mock_pdf.__exit__.return_value = None

        mock_pdfplumber.return_value = mock_pdf

        extractor = BancoChileForeignPDFExtractor()

        with pytest.raises(ValueError, match="Could not extract account number"):
            extractor.extract("fake.pdf")


class TestBancoChileImporterForeignPDF:
    """Test the main importer with foreign currency PDF files."""

    def test_usd_importer_selects_foreign_extractor(self):
        """Test that USD importer uses the foreign PDF extractor."""
        importer = BancoChileImporter(
            account_number="59012345678",
            account_name="Assets:BancoChile:USD",
            currency="USD",
        )

        fake_pdf = Path("test.pdf")
        extractor = importer._get_extractor(fake_pdf)
        assert isinstance(extractor, BancoChileForeignPDFExtractor)

    def test_clp_importer_selects_standard_extractor(self):
        """Test that CLP importer uses the standard PDF extractor."""
        from beancount_chile.extractors.banco_chile_pdf import BancoChilePDFExtractor

        importer = BancoChileImporter(
            account_number="00-123-45678-90",
            account_name="Assets:BancoChile:Checking",
            currency="CLP",
        )

        fake_pdf = Path("test.pdf")
        extractor = importer._get_extractor(fake_pdf)
        assert isinstance(extractor, BancoChilePDFExtractor)

    def test_xls_extractor_unchanged(self):
        """Test that XLS extractor selection is not affected by currency."""
        importer = BancoChileImporter(
            account_number="59012345678",
            account_name="Assets:BancoChile:USD",
            currency="USD",
        )

        fake_xls = Path("test.xls")
        extractor = importer._get_extractor(fake_xls)
        assert extractor == importer.xls_extractor

    @patch("beancount_chile.extractors.banco_chile_foreign_pdf.pdfplumber.open")
    def test_extract_produces_usd_entries(self, mock_pdfplumber):
        """Test that extracted entries use USD currency."""
        page_text = """SR(A)(ES)
Juan Perez Gonzalez
juan@example.com

N° DE CUENTA : 59012345678
CARTOLA N° : 1
DESDE : 01/07/2025 HASTA : 01/07/2025
MONEDA : US DOLLAR

01/07 SALDO INICIAL 0,00
03/06 SRV CPRA USD BANCHILE N°12345678 INTERNET 100,00
03/06 TRANSFERENCIA DE FONDOS INTERNET 20,00 80,00
01/07 SALDO FINAL 80,00"""

        mock_page = MagicMock()
        mock_page.extract_text.return_value = page_text

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__.return_value = mock_pdf
        mock_pdf.__exit__.return_value = None

        mock_pdfplumber.return_value = mock_pdf

        importer = BancoChileImporter(
            account_number="59012345678",
            account_name="Assets:BancoChile:USD",
            currency="USD",
        )

        entries = importer.extract(Path("fake.pdf"))

        # Should have balance + 2 transactions
        assert len(entries) == 3

        # Check that entries use USD currency
        from beancount.core import data

        for entry in entries:
            if isinstance(entry, data.Transaction):
                for posting in entry.postings:
                    assert posting.units.currency == "USD"
            elif isinstance(entry, data.Balance):
                assert entry.amount.currency == "USD"

    @patch("beancount_chile.extractors.banco_chile_foreign_pdf.pdfplumber.open")
    def test_document_number_in_metadata(self, mock_pdfplumber):
        """Test that document numbers are preserved in transaction metadata."""
        page_text = """SR(A)(ES)
Juan Perez Gonzalez
juan@example.com

N° DE CUENTA : 59012345678
CARTOLA N° : 1
DESDE : 01/07/2025 HASTA : 01/07/2025
MONEDA : US DOLLAR

01/07 SALDO INICIAL 0,00
03/06 SRV CPRA USD BANCHILE N°12345678 INTERNET 100,00
01/07 SALDO FINAL 100,00"""

        mock_page = MagicMock()
        mock_page.extract_text.return_value = page_text

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__.return_value = mock_pdf
        mock_pdf.__exit__.return_value = None

        mock_pdfplumber.return_value = mock_pdf

        importer = BancoChileImporter(
            account_number="59012345678",
            account_name="Assets:BancoChile:USD",
            currency="USD",
        )

        entries = importer.extract(Path("fake.pdf"))

        from beancount.core import data

        txn_entries = [e for e in entries if isinstance(e, data.Transaction)]
        assert len(txn_entries) == 1
        assert txn_entries[0].meta["document_number"] == "12345678"

    @patch("beancount_chile.extractors.banco_chile_foreign_pdf.pdfplumber.open")
    def test_filename_includes_currency(self, mock_pdfplumber):
        """Test that filename includes currency for foreign accounts."""
        page_text = """SR(A)(ES)
Juan Perez Gonzalez
juan@example.com

N° DE CUENTA : 59012345678
CARTOLA N° : 1
DESDE : 01/07/2025 HASTA : 01/07/2025
MONEDA : US DOLLAR

01/07 SALDO INICIAL 0,00
03/06 SRV CPRA USD BANCHILE N°12345678 INTERNET 100,00
01/07 SALDO FINAL 100,00"""

        mock_page = MagicMock()
        mock_page.extract_text.return_value = page_text

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__.return_value = mock_pdf
        mock_pdf.__exit__.return_value = None

        mock_pdfplumber.return_value = mock_pdf

        importer = BancoChileImporter(
            account_number="59012345678",
            account_name="Assets:BancoChile:USD",
            currency="USD",
        )

        filename = importer.filename(Path("fake.pdf"))
        assert filename == "2025-07-01_banco_chile_usd_59012345678.pdf"
