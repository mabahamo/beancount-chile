"""Extractor for Banco de Chile foreign currency PDF account statements."""

import re
from datetime import datetime
from decimal import Decimal
from typing import Optional

import pdfplumber

from beancount_chile.extractors.banco_chile_pdf import (
    extract_account_info,
    extract_channel_from_description,
    extract_date_range,
    parse_chilean_date,
)
from beancount_chile.extractors.banco_chile_xls import (
    BancoChileMetadata,
    BancoChileTransaction,
)


def parse_foreign_amount(amount_str: str) -> Decimal:
    """
    Parse foreign currency amount format to Decimal.

    Uses comma as decimal separator and dot as thousands separator.

    Examples:
        '100,00' -> Decimal('100.00')
        '1.234,56' -> Decimal('1234.56')
        '15,00' -> Decimal('15.00')
        '-100,00' -> Decimal('-100.00')
    """
    if not amount_str or amount_str.strip() == "":
        return Decimal("0")

    cleaned = amount_str.strip().replace(" ", "")

    sign = ""
    if cleaned.startswith("-"):
        sign = "-"
        cleaned = cleaned[1:]

    # Remove dots (thousands separators), replace comma with period (decimal)
    cleaned = cleaned.replace(".", "").replace(",", ".")

    try:
        return Decimal(sign + cleaned)
    except Exception:
        return Decimal("0")


def detect_currency_from_header(text: str) -> str:
    """
    Detect currency from MONEDA header line.

    Returns:
        Currency code (e.g., 'USD') or 'CLP' if not found.
    """
    match = re.search(r"MONEDA\s*:?\s*(.+)", text)
    if match:
        moneda = match.group(1).strip().upper()
        if "DOLLAR" in moneda or "USD" in moneda:
            return "USD"
        if "EURO" in moneda or "EUR" in moneda:
            return "EUR"
    return "CLP"


def extract_foreign_account_holder(text: str) -> Optional[str]:
    """
    Extract account holder name from foreign currency PDF header.

    The format uses 'SR(A)(ES)' followed by the name on the next line,
    unlike the CLP format which uses 'Sr(a). : NAME'.

    Returns:
        Account holder name or None
    """
    pattern = r"SR\(A\)\(ES\)\s*\n\s*([A-ZÁÉÍÓÚÑa-záéíóúñ\s]+)"
    match = re.search(pattern, text)
    if match:
        name = match.group(1).strip().split("\n")[0].strip()
        if name:
            return name
    return None


def parse_foreign_transaction_line(
    line: str, year: int
) -> Optional[BancoChileTransaction]:
    """
    Parse a single transaction line from a foreign currency PDF cartola.

    Amount format uses comma as decimal separator (e.g., '100,00').

    Args:
        line: Transaction line text
        year: Year for date parsing

    Returns:
        BancoChileTransaction if successfully parsed, None otherwise
    """
    if not line or "DETALLE DE TRANSACCION" in line or "FECHA" in line:
        return None

    if (
        "SALDO INICIAL" in line
        or "SALDO FINAL" in line
        or "RETENCION" in line
        or "TOTAL CHEQUES" in line
        or "TOTAL DEPOSITOS" in line
        or "SALDO CONTABLE" in line
        or "PARA MAS INFORMACION" in line
        or "QUE BANCO DE CHILE" in line
        or "INFORMATE" in line
    ):
        return None

    # Match date at start of line
    date_pattern = r"^(\d{2}/\d{2})\s+"
    match = re.match(date_pattern, line)
    if not match:
        return None

    date_str = match.group(1)
    date_iso = parse_chilean_date(date_str, year)
    if not date_iso:
        return None

    date = datetime.strptime(date_iso, "%Y-%m-%d")

    # Remove date from line
    rest = line[match.end() :].strip()

    # Extract document number (N°XXXXX) before stripping for amount parsing
    document_number = None
    doc_match = re.search(r"N°(\d+)", rest)
    if doc_match:
        document_number = doc_match.group(1)

    # Remove reference numbers like "N°32323877" before extracting amounts
    rest_for_numbers = re.sub(r"N°\d+", "", rest)

    # Extract all foreign currency amounts (comma as decimal separator)
    # Pattern matches: 100,00  1.234,56  20,00
    number_pattern = r"(?<![A-Za-z])\d+(?:\.\d+)*,\d{2}"
    number_matches = list(re.finditer(number_pattern, rest_for_numbers))
    numbers = [m.group() for m in number_matches]

    if len(numbers) < 1:
        return None

    # Extract description (everything before first amount)
    first_number_pos = number_matches[0].start()
    description = rest_for_numbers[:first_number_pos].strip()

    # Extract channel from description
    description, channel = extract_channel_from_description(description)

    # Parse amounts
    if len(numbers) == 1:
        txn_amount = parse_foreign_amount(numbers[0])
        balance = Decimal("0")
    elif len(numbers) == 2:
        txn_amount = parse_foreign_amount(numbers[0])
        balance = parse_foreign_amount(numbers[1])
    else:
        balance = parse_foreign_amount(numbers[-1])
        txn_amount = sum(parse_foreign_amount(n) for n in numbers[:-1])

    # Determine credit vs debit
    is_ingreso = (
        "SRV CPRA USD" in description
        or "SRV CPRA EUR" in description
        or "TRASPASO DE" in description
        or "TRANSFERENCIA DESDE" in description
        or "TRANSFERENCIA DE OTRO BANCO" in description
        or "Devolucion" in description
        or "REVERSO" in description
        or "PAGO:PROVEEDORES" in description
        or "PAGO:DE SUELDOS" in description
        or "ABONO" in description.upper()
    )

    if is_ingreso:
        debit, credit = None, txn_amount
    else:
        debit, credit = txn_amount, None

    return BancoChileTransaction(
        date=date,
        description=description,
        channel=channel,
        debit=debit,
        credit=credit,
        balance=balance,
        document_number=document_number,
    )


class BancoChileForeignPDFExtractor:
    """Extract transactions from Banco de Chile foreign currency PDF files."""

    def __init__(self):
        """Initialize the extractor."""
        pass

    def get_currency(self, filepath: str) -> str:
        """Detect the currency of the PDF without full extraction."""
        with pdfplumber.open(filepath) as pdf:
            if pdf.pages:
                text = pdf.pages[0].extract_text()
                return detect_currency_from_header(text)
        return "CLP"

    def extract(
        self, filepath: str
    ) -> tuple[BancoChileMetadata, list[BancoChileTransaction]]:
        """
        Extract metadata and transactions from a foreign currency PDF cartola.

        Args:
            filepath: Path to the PDF file

        Returns:
            Tuple of (metadata, transactions)

        Raises:
            ValueError: If the file format is invalid
        """
        transactions = []
        account_holder = None
        account_number = None
        start_date = None
        end_date = None
        closing_balance = None
        currency = "USD"
        year = datetime.now().year

        with pdfplumber.open(filepath) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() + "\n"

            if pdf.pages:
                first_page_text = pdf.pages[0].extract_text()

                # Detect currency
                currency = detect_currency_from_header(first_page_text)

                # Extract dates
                start_date, end_date = extract_date_range(first_page_text)

                if end_date:
                    year = int(end_date.split("-")[0])

                # Extract account info
                account_number, _ = extract_account_info(first_page_text)

                # Extract account holder (foreign format)
                account_holder = extract_foreign_account_holder(first_page_text)

            # Extract closing balance from last page
            if pdf.pages:
                last_page_text = pdf.pages[-1].extract_text()
                saldo_final_pattern = r"SALDO FINAL\s+(\d+(?:\.\d+)*,\d{2})"
                saldo_match = re.search(saldo_final_pattern, last_page_text)
                if saldo_match:
                    closing_balance = parse_foreign_amount(saldo_match.group(1))

            # Parse transactions from all pages
            for page in pdf.pages:
                page_text = page.extract_text()
                lines = page_text.split("\n")

                for line in lines:
                    line = line.strip()
                    transaction = parse_foreign_transaction_line(line, year)
                    if transaction:
                        transactions.append(transaction)

        if not account_number:
            raise ValueError("Could not extract account number from PDF")

        if not end_date:
            raise ValueError("Could not extract statement date from PDF")

        statement_date = datetime.strptime(end_date, "%Y-%m-%d")

        metadata = BancoChileMetadata(
            account_holder=account_holder or "Unknown",
            rut="N/A",
            account_number=account_number,
            currency=currency,
            available_balance=closing_balance or Decimal("0"),
            accounting_balance=closing_balance or Decimal("0"),
            total_debits=sum(
                (t.debit for t in transactions if t.debit), start=Decimal("0")
            ),
            total_credits=sum(
                (t.credit for t in transactions if t.credit), start=Decimal("0")
            ),
            statement_date=statement_date,
        )

        return metadata, transactions
