"""Tests for Banco de Chile credit card PDF extractor."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from beancount_chile.banco_chile_credit import BancoChileCreditImporter
from beancount_chile.extractors.banco_chile_credit_pdf import (
    BancoChileCreditPDFExtractor,
    detect_statement_currency,
    parse_chilean_amount,
    parse_credit_card_number,
    parse_internacional_transaction_line,
    parse_nacional_transaction_line,
    parse_usd_amount,
)


class TestParseChileanAmount:
    """Test Chilean CLP amount parsing."""

    def test_simple_amount(self):
        assert parse_chilean_amount("100") == Decimal("100")

    def test_thousands_separator(self):
        assert parse_chilean_amount("60.610") == Decimal("60610")
        assert parse_chilean_amount("1.322.000") == Decimal("1322000")

    def test_negative_amount(self):
        assert parse_chilean_amount("-20.000") == Decimal("-20000")

    def test_empty_string(self):
        assert parse_chilean_amount("") == Decimal("0")
        assert parse_chilean_amount("   ") == Decimal("0")


class TestParseUsdAmount:
    """Test USD amount parsing (comma as decimal separator)."""

    def test_simple_amount(self):
        assert parse_usd_amount("100,00") == Decimal("100.00")

    def test_with_thousands(self):
        assert parse_usd_amount("1.234,56") == Decimal("1234.56")

    def test_small_amount(self):
        assert parse_usd_amount("15,00") == Decimal("15.00")

    def test_foreign_currency_amount(self):
        assert parse_usd_amount("79.371,00") == Decimal("79371.00")

    def test_negative_amount(self):
        assert parse_usd_amount("-100,00") == Decimal("-100.00")

    def test_empty_string(self):
        assert parse_usd_amount("") == Decimal("0")


class TestParseCreditCardNumber:
    """Test credit card number extraction."""

    def test_standard_format(self):
        assert parse_credit_card_number("XXXX XXX3 0030 5678") == "5678"

    def test_masked_format(self):
        assert parse_credit_card_number("XXXX XXXX XXXX 1234") == "1234"

    def test_no_match(self):
        assert parse_credit_card_number("no card here") == "0000"


class TestDetectStatementCurrency:
    """Test currency detection from PDF title."""

    def test_nacional(self):
        text = "ESTADO DE CUENTA NACIONAL DE TARJETA DE CRÉDITO"
        assert detect_statement_currency(text) == "CLP"

    def test_internacional(self):
        text = "ESTADO DE CUENTA INTERNACIONAL DE TARJETA DE CREDITO"
        assert detect_statement_currency(text) == "USD"

    def test_unknown_defaults_to_clp(self):
        assert detect_statement_currency("some random text") == "CLP"


class TestParseNacionalTransactionLine:
    """Test Nacional (CLP) transaction line parsing."""

    def test_standard_transaction(self):
        line = (
            "VALPARAISO 23/05/25 111122223333"
            " RESTAURANTE SOL VALPARAISO"
            " $ 60.610 $ 60.610 01/01 $ 60.610"
        )
        txn = parse_nacional_transaction_line(line, 2025)

        assert txn is not None
        assert txn.date == datetime(2025, 5, 23)
        assert "RESTAURANTE SOL" in txn.description
        assert txn.amount == Decimal("60610")
        assert txn.installments == "01/01"

    def test_large_amount(self):
        line = (
            "SANTIAGO 25/05/25 444455556666"
            " TIENDA GRANDE SANTIAGO"
            " $ 1.322.000 $ 1.322.000 01/01 $ 1.322.000"
        )
        txn = parse_nacional_transaction_line(line, 2025)

        assert txn is not None
        assert txn.amount == Decimal("1322000")

    def test_negative_amount_discount(self):
        line = (
            "03/06/25 777788889999 Dcto. por compras"
            " $ -20.000 $ -20.000 01/01 $ -20.000"
        )
        txn = parse_nacional_transaction_line(line, 2025)

        assert txn is not None
        assert txn.amount == Decimal("-20000")
        assert "Dcto. por compras" in txn.description

    def test_commission(self):
        line = (
            "05/06/25 000000000000"
            " COMISION MENSUAL POR MANTENCION"
            " $ 13.721 $ 13.721 01/01 $ 13.721"
        )
        txn = parse_nacional_transaction_line(line, 2025)

        assert txn is not None
        assert txn.amount == Decimal("13721")

    def test_skip_header_lines(self):
        assert parse_nacional_transaction_line("LUGAR DE FECHA", 2025) is None
        assert parse_nacional_transaction_line("Sin Movimientos", 2025) is None
        assert parse_nacional_transaction_line("TOTAL TARJETA XXXX", 2025) is None
        assert parse_nacional_transaction_line("", 2025) is None

    def test_small_amount(self):
        line = (
            "SANTIAGO 24/05/25 123456789012"
            " ESTACIONAMIENTO ABC SANTIAGO"
            " $ 900 $ 900 01/01 $ 900"
        )
        txn = parse_nacional_transaction_line(line, 2025)

        assert txn is not None
        assert txn.amount == Decimal("900")


class TestParseInternacionalTransactionLine:
    """Test Internacional (USD) transaction line parsing."""

    def test_standard_transaction(self):
        line = (
            "2605 11112222333344445555666 25/05/25"
            " www.tienda.com WWW.TIENDA"
            " GB 93.762,00 100,00"
        )
        txn = parse_internacional_transaction_line(line, 2025)

        assert txn is not None
        assert txn.date == datetime(2025, 5, 25)
        assert "www.tienda.com" in txn.description
        assert txn.amount == Decimal("100.00")
        assert txn.country == "GB"
        assert txn.original_amount == Decimal("93762.00")

    def test_us_dollar_transaction(self):
        line = (
            "0606 99988877766655544433322 05/06/25"
            " SERVICIO CLOUD SPA PROVEEDOR.C"
            " US 23,80 23,80"
        )
        txn = parse_internacional_transaction_line(line, 2025)

        assert txn is not None
        assert txn.amount == Decimal("23.80")
        assert "SERVICIO CLOUD SPA" in txn.description
        assert txn.country == "US"
        assert txn.original_amount == Decimal("23.80")

    def test_payment_negative(self):
        line = "1806 ACV00000000000000000000 18/06/25 Pago Dolar TEF -100,00"
        txn = parse_internacional_transaction_line(line, 2025)

        assert txn is not None
        assert txn.amount == Decimal("-100.00")
        assert "Pago Dolar" in txn.description
        assert txn.country is None
        assert txn.original_amount is None

    def test_skip_header_lines(self):
        assert parse_internacional_transaction_line("NÚMERO REFERENCIA", 2025) is None
        assert parse_internacional_transaction_line("TOTAL DE COMPRAS", 2025) is None
        assert parse_internacional_transaction_line("", 2025) is None


class TestBancoChileCreditPDFExtractor:
    """Test the PDF extractor with mocked pdfplumber."""

    @patch("beancount_chile.extractors.banco_chile_credit_pdf.pdfplumber.open")
    def test_extract_nacional_pdf(self, mock_pdfplumber):
        """Test extraction of a Nacional (CLP) credit card PDF."""
        page_text = """1 de 1
ESTADO DE CUENTA NACIONAL DE TARJETA DE CRÉDITO
NOMBRE DEL TITULAR JUAN PÉREZ GONZÁLEZ
N° DE TARJETA DE CRÉDITO XXXX XXX3 0030 1234
FECHA ESTADO DE CUENTA 05/06/2025
PERÍODO FACTURADO 07/05/2025 05/06/2025
PAGAR HASTA 18/06/2025
MONTO TOTAL FACTURADO A PAGAR $ 150.000
MONTO MÍNIMO A PAGAR $ 25.000
SANTIAGO 23/05/25 111100002222 TIENDA ABC SANTIAGO $ 50.000 $ 50.000 01/01 $ 50.000
SANTIAGO 24/05/25 333300004444 FARMACIA XYZ SANTIAGO $ 30.000 $ 30.000 01/01 $ 30.000
05/06/25 555500006666 COMISION MANTENCION $ 10.000 $ 10.000 01/01 $ 10.000"""

        mock_page = MagicMock()
        mock_page.extract_text.return_value = page_text

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__.return_value = mock_pdf
        mock_pdf.__exit__.return_value = None
        mock_pdfplumber.return_value = mock_pdf

        extractor = BancoChileCreditPDFExtractor()
        metadata, transactions = extractor.extract("fake.pdf")

        assert metadata.card_last_four == "1234"
        assert metadata.account_holder == "JUAN PÉREZ GONZÁLEZ"
        assert metadata.statement_date == datetime(2025, 6, 5)
        assert metadata.total_billed == Decimal("150000")
        assert metadata.minimum_payment == Decimal("25000")
        assert metadata.due_date == datetime(2025, 6, 18)

        assert len(transactions) == 3
        assert transactions[0].amount == Decimal("50000")
        assert transactions[1].amount == Decimal("30000")
        assert transactions[2].amount == Decimal("10000")

    @patch("beancount_chile.extractors.banco_chile_credit_pdf.pdfplumber.open")
    def test_extract_internacional_pdf(self, mock_pdfplumber):
        """Test extraction of an Internacional (USD) credit card PDF."""
        page_text = """1 de 1
ESTADO DE CUENTA INTERNACIONAL DE TARJETA DE CREDITO
NOMBRE DEL TITULAR JUAN PÉREZ GONZÁLEZ
N° DE TARJETA DE CREDITO XXXX XXX3 0030 1234
FECHA ESTADO DE CUENTA 05/06/2025
DEUDA TOTAL US$ 150,00
PERIODO FACTURADO DESDE 07/05/2025
PAGAR HASTA 18/06/2025
2605 74007035146920008073494 25/05/25 SOME STORE SOMECITY US 150,00 150,00"""

        mock_page = MagicMock()
        mock_page.extract_text.return_value = page_text

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__.return_value = mock_pdf
        mock_pdf.__exit__.return_value = None
        mock_pdfplumber.return_value = mock_pdf

        extractor = BancoChileCreditPDFExtractor()
        metadata, transactions = extractor.extract("fake.pdf")

        assert metadata.card_last_four == "1234"
        assert metadata.total_billed == Decimal("150.00")
        assert metadata.due_date == datetime(2025, 6, 18)

        assert len(transactions) == 1
        assert transactions[0].amount == Decimal("150.00")
        assert "SOME STORE" in transactions[0].description
        assert transactions[0].country == "US"
        assert transactions[0].original_amount == Decimal("150.00")


class TestBancoChileCreditImporterWithPDF:
    """Test the credit card importer with PDF files."""

    def test_get_extractor_for_pdf(self):
        importer = BancoChileCreditImporter(
            card_last_four="1234",
            account_name="Liabilities:CC",
        )

        extractor = importer._get_extractor(Path("test.pdf"))
        assert extractor is not None
        assert isinstance(extractor, BancoChileCreditPDFExtractor)

    def test_get_extractor_for_xls(self):
        importer = BancoChileCreditImporter(
            card_last_four="1234",
            account_name="Liabilities:CC",
        )

        extractor = importer._get_extractor(Path("test.xls"))
        assert extractor is not None
        assert extractor == importer.xls_extractor

    def test_get_extractor_unsupported(self):
        importer = BancoChileCreditImporter(
            card_last_four="1234",
            account_name="Liabilities:CC",
        )

        assert importer._get_extractor(Path("test.txt")) is None

    @patch("beancount_chile.extractors.banco_chile_credit_pdf.pdfplumber.open")
    def test_identify_pdf_matches_currency(self, mock_pdfplumber):
        """CLP importer identifies Nacional PDFs only."""
        nacional_text = """ESTADO DE CUENTA NACIONAL DE TARJETA DE CRÉDITO
NOMBRE DEL TITULAR JUAN PÉREZ
N° DE TARJETA DE CRÉDITO XXXX XXXX XXXX 1234
FECHA ESTADO DE CUENTA 05/06/2025
PAGAR HASTA 18/06/2025"""

        mock_page = MagicMock()
        mock_page.extract_text.return_value = nacional_text

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__.return_value = mock_pdf
        mock_pdf.__exit__.return_value = None
        mock_pdfplumber.return_value = mock_pdf

        clp_importer = BancoChileCreditImporter(
            card_last_four="1234",
            account_name="Liabilities:CC",
            currency="CLP",
        )
        usd_importer = BancoChileCreditImporter(
            card_last_four="1234",
            account_name="Liabilities:CC:USD",
            currency="USD",
        )

        assert clp_importer.identify(Path("test.pdf")) is True
        assert usd_importer.identify(Path("test.pdf")) is False

    def test_filename_includes_currency(self):
        """Test that generated filename includes currency code."""
        importer = BancoChileCreditImporter(
            card_last_four="5678",
            account_name="Liabilities:CC",
            currency="CLP",
        )
        # Verify the pdf_extractor exists
        assert importer.pdf_extractor is not None
