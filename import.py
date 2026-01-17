"""Import configuration for Banco de Chile statements."""

from beangulp import Ingest

from beancount_chile import BancoChileCreditImporter, BancoChileImporter

importers = (
    # Checking account (supports XLS, XLSX, and PDF cartola files)
    BancoChileImporter(
        account_number="00-123-45678-90",
        account_name="Assets:BancoChile:Checking",
        currency="CLP",
    ),
    # Credit card (supports XLS and XLSX - both facturado and no facturado)
    BancoChileCreditImporter(
        card_last_four="1234",
        account_name="Liabilities:CreditCard:BancoChile",
        currency="CLP",
    ),
)

if __name__ == "__main__":
    ingest = Ingest(importers)
    ingest()
