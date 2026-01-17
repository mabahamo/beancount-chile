"""Extractor for Banco de Chile PDF account statements (cartola)."""

import re
from datetime import datetime
from decimal import Decimal
from typing import Optional

import pdfplumber

from beancount_chile.extractors.banco_chile_xls import (
    BancoChileMetadata,
    BancoChileTransaction,
)


def parse_chilean_amount(amount_str: str) -> Decimal:
    """
    Parse Chilean currency format to Decimal.

    Examples:
        '75.000' -> 75000
        '1.234.567' -> 1234567
        '100' -> 100

    Args:
        amount_str: Amount string in Chilean format

    Returns:
        Decimal representation of the amount
    """
    if not amount_str or amount_str.strip() == "":
        return Decimal("0")

    # Remove spaces and any non-numeric characters except dots
    cleaned = amount_str.strip().replace(" ", "")

    # Remove dots (thousand separators in Chilean format)
    cleaned = cleaned.replace(".", "")

    # Convert to Decimal
    try:
        return Decimal(cleaned)
    except Exception:
        return Decimal("0")


def parse_chilean_date(date_str: str, year: int) -> Optional[str]:
    """
    Parse Chilean date format to ISO format.

    Examples:
        '02/01' with year 2025 -> '2025-01-02'
        '31/12' with year 2024 -> '2024-12-31'

    Args:
        date_str: Date string in DD/MM format
        year: Year to use for the date

    Returns:
        Date string in YYYY-MM-DD format
    """
    try:
        day, month = date_str.split("/")
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    except Exception:
        return None


def extract_date_range(text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extract date range from cartola header.

    Looks for 'DESDE : DD/MM/YYYY HASTA : DD/MM/YYYY'

    Returns:
        Tuple of (start_date, end_date) in YYYY-MM-DD format
    """
    # Pattern: DESDE : DD/MM/YYYY HASTA : DD/MM/YYYY
    pattern = r"DESDE\s*:\s*(\d{2}/\d{2}/\d{4})\s+HASTA\s*:\s*(\d{2}/\d{2}/\d{4})"
    match = re.search(pattern, text)

    if match:
        start_str = match.group(1)  # DD/MM/YYYY
        end_str = match.group(2)  # DD/MM/YYYY

        # Convert to YYYY-MM-DD
        start_parts = start_str.split("/")
        start_date = f"{start_parts[2]}-{start_parts[1]}-{start_parts[0]}"

        end_parts = end_str.split("/")
        end_date = f"{end_parts[2]}-{end_parts[1]}-{end_parts[0]}"

        return start_date, end_date

    return None, None


def extract_account_info(text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extract account number and cartola number from header.

    Returns:
        Tuple of (account_number, cartola_number)
    """
    # Pattern for account number: N° DE CUENTA : XXXXXXXXXX
    account_pattern = r"N°\s*DE\s*CUENTA\s*:\s*(\d+[-\d]*)"
    account_match = re.search(account_pattern, text)
    account_number = account_match.group(1) if account_match else None

    # Pattern for cartola number: CARTOLA N° : X
    cartola_pattern = r"CARTOLA\s*N°\s*:\s*(\d+)"
    cartola_match = re.search(cartola_pattern, text)
    cartola_number = cartola_match.group(1) if cartola_match else None

    return account_number, cartola_number


def extract_account_holder_and_rut(text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extract account holder name and RUT from header.

    The PDF typically has a pattern like:
    "Sr(a). : NOMBRE COMPLETO"
    "RUT : XX.XXX.XXX-X"

    Returns:
        Tuple of (account_holder, rut)
    """
    # Pattern for account holder
    # Matches "Sr(a). : NAME" or "Sr(a): NAME" or "Sr(a) : NAME"
    # with various letter types. Allows optional period and/or colon.
    holder_pattern = r"Sr\(?a?\)?\.?\s*:\s*([A-ZÁÉÍÓÚÑa-záéíóúñ\s]+)"
    holder_match = re.search(holder_pattern, text)
    if holder_match:
        # Clean up the matched name (remove extra whitespace, stop at newline/RUT)
        raw_name = holder_match.group(1).strip()
        # Stop at newline or before RUT keyword
        name_parts = raw_name.split("\n")[0].split("RUT")[0].strip()
        account_holder = name_parts if name_parts else None
    else:
        account_holder = None

    # Pattern for RUT
    rut_pattern = r"RUT\s*:\s*([\d.]+-[\dkK])"
    rut_match = re.search(rut_pattern, text)
    rut = rut_match.group(1) if rut_match else None

    return account_holder, rut


def parse_transaction_line(line: str, year: int) -> Optional[BancoChileTransaction]:
    """
    Parse a single transaction line from the cartola PDF.

    Expected format:
    DD/MM DESCRIPTION [SUCURSAL] [N° DOCTO] [DEBIT] [CREDIT] BALANCE

    The PDF has implicit columns:
    - MONTO CHEQUES O CARGOS (debits)
    - MONTO DEPOSITOS O ABONOS (credits)
    - SALDO (balance)

    Special cases:
    - Check deposits: DD/MM DEP.CHEQ.OTROS BANCOS [OFFICE] [CHECK#]
      [AMOUNT] [BALANCE]
    - Check returned: DD/MM CHEQUE DEPOSITADO DEVUELTO [OFFICE]
      [CHECK#] [AMOUNT] [BALANCE]
    - PAGO transactions with folio numbers (10 digits starting with 0)

    Args:
        line: Transaction line text
        year: Year for date parsing

    Returns:
        BancoChileTransaction if successfully parsed, None otherwise
    """
    # Skip header lines and empty lines
    if not line or "DETALLE DE TRANSACCION" in line or "FECHA" in line:
        return None

    # Skip special rows
    if (
        "SALDO INICIAL" in line
        or "SALDO FINAL" in line
        or "RETENCION" in line
        or "PARA MAS INFORMACION" in line
        or "QUE BANCO DE CHILE" in line
        or "INFORMATE" in line
    ):
        return None

    # Special case: Check deposit (ingreso)
    # Format: DD/MM DEP.CHEQ.OTROS BANCOS [OFFICE] [8-DIGIT CHECK #] [AMOUNT] [BALANCE]
    cheque_pattern = r"^(\d{2}/\d{2}).*DEP.*CHEQ.* (\d{8}) ([\d.]+)\s*([\d.]+)?$"
    cheque_match = re.match(cheque_pattern, line)
    if cheque_match:
        date_str = cheque_match.group(1)
        date_iso = parse_chilean_date(date_str, year)
        if not date_iso:
            return None

        date = datetime.strptime(date_iso, "%Y-%m-%d")
        amount = parse_chilean_amount(cheque_match.group(3))
        balance = (
            parse_chilean_amount(cheque_match.group(4))
            if cheque_match.group(4)
            else Decimal("0")
        )

        return BancoChileTransaction(
            date=date,
            description="DEP.CHEQ.OTROS BANCOS",
            channel="",
            debit=None,
            credit=amount,
            balance=balance,
        )

    # Special case: Check returned (egreso)
    # Format: DD/MM CHEQUE DEPOSITADO DEVUELTO [OFFICE] [8-DIGIT CHECK #]
    # [AMOUNT] [BALANCE]
    devuelto_pattern = (
        r"^(\d{2}/\d{2}).*CHEQUE DEPOSITADO DEVUELTO.* (\d{8}) ([\d.]+)\s*([\d.]+)?$"
    )
    devuelto_match = re.match(devuelto_pattern, line)
    if devuelto_match:
        date_str = devuelto_match.group(1)
        date_iso = parse_chilean_date(date_str, year)
        if not date_iso:
            return None

        date = datetime.strptime(date_iso, "%Y-%m-%d")
        amount = parse_chilean_amount(devuelto_match.group(3))
        balance = (
            parse_chilean_amount(devuelto_match.group(4))
            if devuelto_match.group(4)
            else Decimal("0")
        )

        return BancoChileTransaction(
            date=date,
            description="CHEQUE DEPOSITADO DEVUELTO",
            channel="",
            debit=amount,
            credit=None,
            balance=balance,
        )

    # Parse the line
    # Pattern: DD/MM Description [amounts]
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

    # Extract all numbers from the line
    number_pattern = r"\d+(?:\.\d+)*"
    numbers = re.findall(number_pattern, rest)

    if len(numbers) < 1:
        return None

    # Find where numbers start in the string to extract description
    first_number_pos = rest.find(numbers[0])
    description = rest[:first_number_pos].strip()

    # Special case: PAGO transactions have the folio number embedded
    # Format: "PAGO:Devolucion 0764749650" or "PAGO:PROVEEDORES 0776016489"
    # The long number is the folio, not the amount
    if (
        "PAGO:DEVOLUCION" in description.upper()
        or "PAGO:DEVOLUCIÓN" in description.upper()
        or "PAGO:PROVEEDORES" in description
    ):
        # Remove the folio number from numbers list
        # (it's usually 10 digits starting with 0)
        filtered_numbers = []
        for num in numbers:
            # Skip numbers that look like folios (10 digits, starts with 0)
            if len(num.replace(".", "")) == 10 and num.startswith("0"):
                # Add folio to description instead
                description = description + " " + num
            else:
                filtered_numbers.append(num)
        numbers = filtered_numbers

    # Determine which numbers are debit/credit/balance
    # The format from the PDF is: [DEBIT or CREDIT] BALANCE
    # - If only 1 number: that's the balance (transaction continues on next line)
    # - If 2 numbers: first is amount (debit or credit), second is balance
    # - If 3+ numbers: last is balance, sum others as amount

    debit = None
    credit = None
    balance = Decimal("0")

    if len(numbers) == 0:
        # No valid numbers found - skip this transaction
        return None

    elif len(numbers) == 1:
        # Only amount shown - no balance on this line
        amount = parse_chilean_amount(numbers[0])
        balance = Decimal("0")  # No balance shown on this line

        # Determine if it's a credit (ingreso) or debit (egreso)
        is_ingreso = (
            "TRASPASO DE" in description
            or "Devolucion" in description
            or "REVERSO" in description
            or "PAGO:PROVEEDORES" in description
        )

        if is_ingreso:
            credit = amount
            debit = None
        else:
            debit = amount
            credit = None

    elif len(numbers) == 2:
        # Format: AMOUNT BALANCE
        amount = parse_chilean_amount(numbers[0])
        balance = parse_chilean_amount(numbers[1])

        # Determine if it's a credit (ingreso) or debit (egreso)
        is_ingreso = (
            "TRASPASO DE" in description
            or "Devolucion" in description
            or "REVERSO" in description
            or "PAGO:PROVEEDORES" in description
        )

        if is_ingreso:
            credit = amount
            debit = None
        else:
            debit = amount
            credit = None

    else:
        # 3+ numbers: last is balance, sum others as amount
        balance = parse_chilean_amount(numbers[-1])
        total_amount = sum(parse_chilean_amount(n) for n in numbers[:-1])

        # Determine if it's a credit (ingreso) or debit (egreso)
        is_ingreso = (
            "TRASPASO DE" in description
            or "Devolucion" in description
            or "REVERSO" in description
            or "PAGO:PROVEEDORES" in description
        )

        if is_ingreso:
            credit = total_amount
            debit = None
        else:
            debit = total_amount
            credit = None

    return BancoChileTransaction(
        date=date,
        description=description,
        channel="",  # PDF doesn't have channel info
        debit=debit,
        credit=credit,
        balance=balance,
    )


class BancoChilePDFExtractor:
    """Extract transactions from Banco de Chile PDF files (cartola)."""

    def __init__(self):
        """Initialize the extractor."""
        pass

    def extract(
        self, filepath: str
    ) -> tuple[BancoChileMetadata, list[BancoChileTransaction]]:
        """
        Extract metadata and transactions from a Banco de Chile PDF cartola.

        Args:
            filepath: Path to the PDF file

        Returns:
            Tuple of (metadata, transactions)

        Raises:
            ValueError: If the file format is invalid
        """
        transactions = []
        account_holder = None
        rut = None
        account_number = None
        start_date = None
        end_date = None
        closing_balance = None
        year = datetime.now().year

        with pdfplumber.open(filepath) as pdf:
            # Extract text from all pages
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() + "\n"

            # Extract header information from first page
            if pdf.pages:
                first_page_text = pdf.pages[0].extract_text()

                # Extract dates
                start_date, end_date = extract_date_range(first_page_text)

                # Determine year from end_date
                if end_date:
                    year = int(end_date.split("-")[0])

                # Extract account info
                account_number, _ = extract_account_info(first_page_text)

                # Extract account holder and RUT
                account_holder, rut = extract_account_holder_and_rut(first_page_text)

            # Extract closing balance from last page
            if pdf.pages:
                last_page_text = pdf.pages[-1].extract_text()
                saldo_final_pattern = r"SALDO FINAL\s+(\d+(?:\.\d+)*)"
                saldo_match = re.search(saldo_final_pattern, last_page_text)
                if saldo_match:
                    closing_balance = parse_chilean_amount(saldo_match.group(1))

            # Parse transactions from all pages
            for page in pdf.pages:
                page_text = page.extract_text()
                lines = page_text.split("\n")

                for line in lines:
                    # Strip leading/trailing whitespace
                    line = line.strip()
                    transaction = parse_transaction_line(line, year)
                    if transaction:
                        transactions.append(transaction)

        # Create metadata
        # Note: PDF doesn't have all fields that XLS has, so we use defaults
        if not account_number:
            raise ValueError("Could not extract account number from PDF")

        if not end_date:
            raise ValueError("Could not extract statement date from PDF")

        statement_date = datetime.strptime(end_date, "%Y-%m-%d")

        metadata = BancoChileMetadata(
            account_holder=account_holder or "Unknown",
            rut=rut or "Unknown",
            account_number=account_number,
            currency="CLP",
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
