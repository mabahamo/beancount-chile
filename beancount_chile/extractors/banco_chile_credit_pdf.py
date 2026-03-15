"""Extractor for Banco de Chile credit card PDF statements."""

import re
from datetime import datetime
from decimal import Decimal
from typing import Optional

import pdfplumber

from beancount_chile.extractors.banco_chile_credit_xls import (
    BancoChileCreditMetadata,
    BancoChileCreditTransaction,
    StatementType,
)


def parse_chilean_amount(amount_str: str) -> Decimal:
    """
    Parse Chilean currency format to Decimal (dots as thousands).

    Examples:
        '60.610' -> 60610
        '1.234.567' -> 1234567
        '100' -> 100
    """
    if not amount_str or amount_str.strip() == "":
        return Decimal("0")
    cleaned = amount_str.strip().replace(" ", "").replace(".", "")
    try:
        return Decimal(cleaned)
    except Exception:
        return Decimal("0")


def parse_usd_amount(amount_str: str) -> Decimal:
    """
    Parse USD amount format used in Chilean international statements.

    Comma is decimal separator, dot is thousands separator.

    Examples:
        '100,00' -> 100.00
        '1.234,56' -> 1234.56
        '15,00' -> 15.00
        '79.371,00' -> 79371.00
        '-100,00' -> -100.00
    """
    if not amount_str or amount_str.strip() == "":
        return Decimal("0")
    cleaned = amount_str.strip().replace(" ", "")
    # Preserve sign
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


def parse_credit_card_number(text: str) -> str:
    """
    Extract last 4 digits from credit card number line.

    Examples:
        'XXXX XXX3 0030 4545' -> '4545'
        'XXXX XXXX XXXX 1234' -> '1234'
    """
    # Match the last group of 4 digits
    match = re.search(r"(\d{4})\s*$", text.strip())
    if match:
        return match.group(1)
    return "0000"


def detect_statement_currency(text: str) -> str:
    """
    Detect statement currency from PDF title.

    Returns:
        'CLP' for Nacional statements, 'USD' for Internacional statements.
    """
    if "INTERNACIONAL" in text.upper():
        return "USD"
    if "NACIONAL" in text.upper():
        return "CLP"
    # Default to CLP
    return "CLP"


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse DD/MM/YYYY or DD/MM/YY date string."""
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def parse_nacional_transaction_line(
    line: str, year: int
) -> Optional[BancoChileCreditTransaction]:
    """
    Parse a Nacional (CLP) credit card transaction line from the PDF.

    Format examples:
        CITY DD/MM/YY CODE DESCRIPTION CITY2 $ AMOUNT $ TOTAL NN/NN $ INST_AMOUNT
        DD/MM/YY CODE DESCRIPTION $ -AMOUNT $ -AMOUNT NN/NN $ -AMOUNT

    Returns:
        BancoChileCreditTransaction or None if line doesn't match.
    """
    if not line or not line.strip():
        return None

    line = line.strip()

    # Skip header/summary lines
    skip_patterns = [
        "LUGAR DE",
        "OPERACIÓN",
        "CUOTA",
        "O COBRO",
        "Sin Movimientos",
        "TOTAL ",
        "EMISOR",
        "COMPROBANTE",
        "NOMBRE",
        "PAGAR HASTA",
        "MONTO",
        "Timbre",
        "Estimado cliente",
        "debe completar",
        "casilleros",
        "CLIENTE",
        "Cheque",
        "Efectivo",
        "PERÍODO",
        "SALDO",
        "CARGO",
        "INFORMACIÓN",
        "VENCIMIENTO",
        "PRÓXIMO",
        "INTERÉS",
        "COSTOS",
        "LOS PAGOS",
        "CONCEPTO",
        "DE ACUERDO",
        "TELEFÓNICA",
        "CAE",
        "CUPO",
        "TASA",
        "DESDE",
        "Infórmese",
        "inscritas",
        "ROTATIVO",
        "ESTADO DE CUENTA",
        "N° DE TARJETA",
        "FECHA ESTADO",
        "1.",
        "2.",
        "3.",
        "4.",
        "I.",
        "II.",
        "III.",
        "IV.",
        "de 3",
        "de 2",
        "de 1",
        "de 4",
        "de 5",
    ]

    for pattern in skip_patterns:
        if line.startswith(pattern):
            return None

    # Pattern: [CITY] DD/MM/YY CODE DESCRIPTION [CITY2] $ AMOUNT $ TOTAL NN/NN $ INST
    # Extract date (DD/MM/YY)
    date_match = re.search(r"(\d{2}/\d{2}/\d{2})\s+", line)
    if not date_match:
        return None

    date = _parse_date(date_match.group(1))
    if not date:
        return None

    # Extract the part after the date
    after_date = line[date_match.end() :]

    # Extract code (digits) and description
    code_match = re.match(r"(\d+)\s+(.+)", after_date)
    if not code_match:
        return None

    description_and_amounts = code_match.group(2)

    # Extract amounts: look for $ followed by amounts
    # Pattern: $ AMOUNT $ TOTAL NN/NN $ INST_AMOUNT
    # The amounts can be negative (prefixed with -)
    amount_pattern = r"\$\s*(-?[\d.]+)"
    amounts = re.findall(amount_pattern, description_and_amounts)

    if not amounts:
        return None

    # First $ amount is the operation amount, second is total to pay
    operation_amount = parse_chilean_amount(amounts[0])

    # Extract installments (NN/NN pattern)
    installment_match = re.search(r"(\d{2}/\d{2})", description_and_amounts)
    installments = None
    if installment_match:
        candidate = installment_match.group(1)
        # Make sure it's not the date (which we already matched)
        if candidate != date_match.group(1)[:5]:
            installments = candidate

    # Extract description: everything before the first $ sign
    desc_parts = description_and_amounts.split("$")[0].strip()
    # The description may end with a city name - keep it as is
    description = desc_parts.strip()

    return BancoChileCreditTransaction(
        date=date,
        description=description,
        amount=operation_amount,
        installments=installments,
        category=None,
    )


def parse_internacional_transaction_line(
    line: str, year: int
) -> Optional[BancoChileCreditTransaction]:
    """
    Parse an Internacional (USD) credit card transaction line from the PDF.

    Format examples:
        NNNN REFERENCE DD/MM/YY DESCRIPTION CITY COUNTRY FOREIGN_AMOUNT USD_AMOUNT
        NNNN REFERENCE DD/MM/YY Pago Dolar TEF -USD_AMOUNT

    Returns:
        BancoChileCreditTransaction or None if line doesn't match.
    """
    if not line or not line.strip():
        return None

    line = line.strip()

    # Skip header/summary lines
    skip_patterns = [
        "NÚMERO",
        "INTERNACIONAL",
        "ORIGEN",
        "TOTAL ",
        "COMPROBANTE",
        "Nombre",
        "Pagar",
        "Monto",
        "US$",
        "ESTADO",
        "NOMBRE",
        "N°",
        "FECHA ESTADO",
        "INFORMACION",
        "CUPO",
        "II.",
        "I.",
        "1.",
        "2.",
        "SALDO",
        "ABONO",
        "TRASPASO",
        "DEUDA",
        "Infórmese",
        "la CMF",
        "Timbre",
        "Banco",
        "de 1",
        "de 2",
        "de 3",
    ]

    for pattern in skip_patterns:
        if line.startswith(pattern):
            return None

    # Pattern: NNNN REFERENCE DD/MM/YY DESCRIPTION CITY COUNTRY [FOREIGN_AMOUNT] USD_AMOUNT
    # The line starts with a 4-digit number
    match = re.match(
        r"(\d{4})\s+(\S+)\s+(\d{2}/\d{2}/\d{2})\s+(.+)",
        line,
    )
    if not match:
        return None

    date = _parse_date(match.group(3))
    if not date:
        return None

    rest = match.group(4)

    # Extract USD amounts from the end of the line
    # They use comma as decimal separator: 100,00 or -100,00
    # There may be 1 or 2 amounts at the end
    amount_pattern = r"(-?[\d.,]+)$"
    amounts = []
    remaining = rest.strip()

    # Try to extract amounts from the end
    while True:
        m = re.search(amount_pattern, remaining)
        if not m:
            break
        amounts.insert(0, m.group(1))
        remaining = remaining[: m.start()].strip()
        if len(amounts) >= 2:
            break

    if not amounts:
        return None

    # The last amount is the USD amount
    usd_amount = parse_usd_amount(amounts[-1])

    # The description is the remaining text after removing amounts
    # Also extract country code (2 letters at the end of remaining)
    description = remaining.strip()

    # Try to extract country code from end of description
    country_match = re.search(r"\s+([A-Z]{2})\s*$", description)
    if country_match:
        description = description[: country_match.start()].strip()

    return BancoChileCreditTransaction(
        date=date,
        description=description,
        amount=usd_amount,
        installments=None,
        category=None,
    )


class BancoChileCreditPDFExtractor:
    """Extract transactions from Banco de Chile credit card PDF statements."""

    def __init__(self):
        pass

    def extract(
        self, filepath: str
    ) -> tuple[BancoChileCreditMetadata, list[BancoChileCreditTransaction]]:
        """
        Extract metadata and transactions from a credit card PDF statement.

        Returns:
            Tuple of (metadata, transactions)

        Raises:
            ValueError: If the file format is invalid
        """
        with pdfplumber.open(filepath) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() + "\n"

        currency = detect_statement_currency(full_text)

        # Extract metadata
        metadata = self._extract_metadata(full_text, currency)

        # Extract transactions
        transactions = self._extract_transactions(full_text, currency)

        return metadata, transactions

    def _extract_metadata(
        self, text: str, currency: str
    ) -> BancoChileCreditMetadata:
        """Extract metadata from the PDF text."""
        # Card holder
        holder_match = re.search(r"NOMBRE DEL TITULAR\s+(.+)", text)
        account_holder = holder_match.group(1).strip() if holder_match else "Unknown"

        # Card number - extract last 4 digits
        card_match = re.search(
            r"N[°º]\s*DE\s*TARJETA\s*DE\s*CR[ÉE]DITO\s+(.+)", text
        )
        card_last_four = "0000"
        if card_match:
            card_last_four = parse_credit_card_number(card_match.group(1))

        # Statement date
        date_match = re.search(
            r"FECHA\s+ESTADO\s+DE\s+CUENTA\s+(\d{2}/\d{2}/\d{4})", text
        )
        statement_date = datetime.now()
        if date_match:
            parsed = _parse_date(date_match.group(1))
            if parsed:
                statement_date = parsed

        # Billing period
        billing_start = None
        billing_end = None
        period_match = re.search(
            r"PER[ÍI]ODO\s+FACTURADO\s+(?:DESDE\s+)?(\d{2}/\d{2}/\d{4})\s+"
            r"(?:HASTA\s+)?(\d{2}/\d{2}/\d{4})?",
            text,
        )
        if not period_match:
            period_match = re.search(
                r"PERIODO\s+FACTURADO\s+DESDE\s+(\d{2}/\d{2}/\d{4})", text
            )
        if period_match:
            billing_start = _parse_date(period_match.group(1))
            if period_match.lastindex and period_match.lastindex >= 2:
                billing_end = _parse_date(period_match.group(2))

        # Due date
        due_date = None
        due_match = re.search(r"PAGAR\s+HASTA\s+(\d{2}/\d{2}/\d{4})", text)
        if due_match:
            due_date = _parse_date(due_match.group(1))

        # Total billed / Total debt
        total_billed = None
        if currency == "CLP":
            total_match = re.search(
                r"MONTO\s+TOTAL\s+FACTURADO\s+A\s+PAGAR.*?\$\s*([\d.]+)", text
            )
            if total_match:
                total_billed = parse_chilean_amount(total_match.group(1))

            # Minimum payment
            min_match = re.search(
                r"MONTO\s+M[ÍI]NIMO\s+A\s+PAGAR\s+\$\s*([\d.]+)", text
            )
            minimum_payment = (
                parse_chilean_amount(min_match.group(1)) if min_match else None
            )
        else:
            total_match = re.search(r"DEUDA\s+TOTAL\s+US\$\s*([\d.,]+)", text)
            if total_match:
                total_billed = parse_usd_amount(total_match.group(1))
            minimum_payment = None

        # RUT - not typically in credit card PDFs
        rut = "Unknown"

        metadata = BancoChileCreditMetadata(
            account_holder=account_holder,
            rut=rut,
            card_type="PDF",
            card_last_four=card_last_four,
            card_status="Active",
            statement_type=StatementType.FACTURADO,
            statement_date=statement_date,
            total_billed=total_billed,
            minimum_payment=minimum_payment,
            billing_date=billing_start,
            due_date=due_date,
        )

        return metadata

    def _extract_transactions(
        self, text: str, currency: str
    ) -> list[BancoChileCreditTransaction]:
        """Extract transactions from the PDF text."""
        transactions = []
        lines = text.split("\n")

        # Determine year from statement date
        date_match = re.search(
            r"FECHA\s+ESTADO\s+DE\s+CUENTA\s+(\d{2}/\d{2}/\d{4})", text
        )
        year = datetime.now().year
        if date_match:
            parsed = _parse_date(date_match.group(1))
            if parsed:
                year = parsed.year

        parser = (
            parse_nacional_transaction_line
            if currency == "CLP"
            else parse_internacional_transaction_line
        )

        for line in lines:
            txn = parser(line.strip(), year)
            if txn:
                transactions.append(txn)

        return transactions

    def get_currency(self, filepath: str) -> str:
        """
        Detect the currency of a PDF statement without full extraction.

        Returns:
            'CLP' or 'USD'
        """
        with pdfplumber.open(filepath) as pdf:
            if pdf.pages:
                first_page_text = pdf.pages[0].extract_text()
                return detect_statement_currency(first_page_text)
        return "CLP"
