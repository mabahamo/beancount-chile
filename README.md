# beancount-chile

Beancount importers for Chilean banks using the [beangulp](https://github.com/beancount/beangulp) framework.

This project provides importers for various Chilean bank account statement formats, enabling automatic import of transactions into [Beancount](https://github.com/beancount/beancount) for double-entry bookkeeping.

## Supported Banks and Formats

| Bank | Format | Status | File Extension |
|------|--------|--------|----------------|
| Banco de Chile | Cartola (Account Statement) | ✅ Supported | .xls, .xlsx, .pdf |
| Banco de Chile | Credit Card Statements (Facturado/No Facturado) | ✅ Supported | .xls, .xlsx |

## Installation

### Prerequisites

- Python 3.10 or higher
- Beancount 3.x

### From Source

```bash
git clone https://github.com/yourusername/beancount-chile.git
cd beancount-chile

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install in development mode
pip install -e .
```

## Usage

### Banco de Chile Importer

The Banco de Chile importer supports XLS/XLSX/PDF account statement files (cartola).

#### Basic Usage

Create a configuration file (e.g., `import_config.py`):

```python
from beancount_chile import BancoChileImporter, BancoChileCreditImporter

CONFIG = [
    # Checking account
    BancoChileImporter(
        account_number="00-123-45678-90",  # Your account number
        account_name="Assets:BancoChile:Checking",
        currency="CLP",
    ),
    # Credit card
    BancoChileCreditImporter(
        card_last_four="1234",  # Last 4 digits of your card
        account_name="Liabilities:CreditCard:BancoChile",
        currency="CLP",
    ),
]
```

#### Import Transactions

Use beangulp to extract transactions:

```bash
# Identify which importers can handle your files
bean-extract import_config.py ~/Downloads/

# Extract transactions from a specific file (XLS, XLSX, or PDF)
bean-extract import_config.py ~/Downloads/cartola.xls
bean-extract import_config.py ~/Downloads/cartola.pdf

# Extract and append to your beancount file
bean-extract import_config.py ~/Downloads/cartola.pdf >> accounts.beancount
```

**Note**: The importer automatically detects the file format (XLS/XLSX/PDF) and uses the appropriate parser. PDF files are parsed using text extraction, which handles the same transaction types as XLS files.

#### Example Output

The importer will generate Beancount entries like:

```beancount
2026-01-01 * "Supermercado Santa Isabel" "Supermercado Santa Isabel"
  channel: "Internet"
  Assets:BancoChile:Checking  -45000 CLP

2026-01-03 * "María González" "Traspaso A:María González"
  channel: "Internet"
  Assets:BancoChile:Checking  -125000 CLP

2026-01-05 balance Assets:BancoChile:Checking  1230000 CLP
```

### Banco de Chile Credit Card Importer

The credit card importer supports both billed (Facturado) and unbilled (No Facturado) statements.

#### Basic Usage

The credit card importer automatically detects whether a file contains billed or unbilled transactions:

```python
from beancount_chile import BancoChileCreditImporter

CONFIG = [
    BancoChileCreditImporter(
        card_last_four="1234",  # Last 4 digits of your card
        account_name="Liabilities:CreditCard:BancoChile",
        currency="CLP",
    ),
]
```

#### Example Output

**Billed Transactions** (Mov_Facturado.xls):
```beancount
2026-01-08 note Liabilities:CreditCard:BancoChile "Credit Card Statement - FACTURADO (Billed) | Total Billed: $850,000 CLP | Minimum Payment: $42,500 CLP | Due Date: 2026-01-21"

2026-01-02 * "SUPERMERCADO JUMBO" "SUPERMERCADO JUMBO SANTIAGO"
  statement_type: "facturado"
  category: "Total de Pagos, Compras, Cuotas y Avance"
  installments: "01/01"
  Liabilities:CreditCard:BancoChile  75000 CLP
```

**Unbilled Transactions** (Saldo_y_Mov_No_Facturado.xls):
```beancount
2026-01-16 note Liabilities:CreditCard:BancoChile "Credit Card Statement - NO FACTURADO (Unbilled) | Available Credit: $6,500,000 CLP | Total Limit: $7,000,000 CLP"

2026-01-16 ! "NETFLIX.COM" "NETFLIX.COM COMPRAS"
  statement_type: "no_facturado"
  city: "LAS CONDES"
  installments: "01/01"
  Liabilities:CreditCard:BancoChile  12000 CLP
```

Note: Billed transactions are marked as cleared (`*`) while unbilled transactions are marked as pending (`!`).

### Features

- **Automatic payee extraction**: Extracts payee names from transaction descriptions
- **Balance assertions**: Adds balance assertions to verify account balances
- **Metadata tracking**: Preserves channel information (Internet, Sucursal, etc.)
- **Deduplication support**: Works with beangulp's existing entry detection

## Development

### Running Tests

```bash
# Activate virtual environment
source venv/bin/activate

# Run all tests
pytest

# Run with coverage
pytest --cov=beancount_chile

# Run specific test file
pytest tests/test_banco_chile.py -v
```

### Code Quality

```bash
# Format code with ruff
ruff format .

# Lint code
ruff check .

# Fix auto-fixable issues
ruff check --fix .
```

### Project Structure

```
beancount-chile/
├── beancount_chile/                   # Main package
│   ├── __init__.py
│   ├── banco_chile.py                 # Checking account importer
│   ├── banco_chile_credit.py          # Credit card importer
│   ├── helpers.py                     # Shared utilities
│   └── extractors/                    # File format parsers
│       ├── __init__.py
│       ├── banco_chile_xls.py         # Checking account XLS parser
│       ├── banco_chile_pdf.py         # Checking account PDF parser
│       └── banco_chile_credit_xls.py  # Credit card parser
├── tests/                             # Test suite
│   ├── __init__.py
│   ├── test_banco_chile.py            # Checking account tests
│   ├── test_banco_chile_credit.py     # Credit card tests
│   ├── test_banco_chile_pdf.py        # PDF parser tests
│   └── fixtures/                      # Test data (anonymized)
│       ├── banco_chile_cartola_sample.xls
│       ├── banco_chile_credit_facturado_sample.xls
│       └── banco_chile_credit_no_facturado_sample.xls
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Contributing

Contributions are welcome! To add support for a new bank:

1. Fork the repository
2. Create a feature branch
3. Add the importer in `beancount_chile/`
4. Add an extractor in `beancount_chile/extractors/`
5. Create anonymized test fixtures in `tests/fixtures/`
6. Write comprehensive tests
7. Update this README
8. Submit a pull request

### Guidelines

- **Privacy**: Never commit real bank data. All test fixtures must use anonymized data.
- **Testing**: Every importer must have comprehensive tests.
- **Documentation**: Update README.md and CLAUDE.md with new features.
- **Code Quality**: Follow PEP 8 and use ruff for linting.

## License

MIT License

## Disclaimer

This project is not affiliated with any bank. Use at your own risk. Always verify imported transactions against your bank statements.

## Support

For issues, questions, or contributions, please open an issue on GitHub.
