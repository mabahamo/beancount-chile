# beancount-chile

Beancount importers for Chilean banks using the [beangulp](https://github.com/beancount/beangulp) framework.

This project provides importers for various Chilean bank account statement formats, enabling automatic import of transactions into [Beancount](https://github.com/beancount/beancount) for double-entry bookkeeping.

## Supported Banks and Formats

| Bank | Format | Status | File Extension |
|------|--------|--------|----------------|
| Banco de Chile | Cartola (Account Statement) | ✅ Supported | .xls, .xlsx |

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

The Banco de Chile importer supports XLS/XLSX account statement files (cartola).

#### Basic Usage

Create a configuration file (e.g., `import_config.py`):

```python
from beancount_chile import BancoChileImporter

CONFIG = [
    BancoChileImporter(
        account_number="00-123-45678-90",  # Your account number
        account_name="Assets:BancoChile:Checking",
        currency="CLP",
    ),
]
```

#### Import Transactions

Use beangulp to extract transactions:

```bash
# Identify which importers can handle your files
bean-extract import_config.py ~/Downloads/

# Extract transactions from a specific file
bean-extract import_config.py ~/Downloads/cartola.xls

# Extract and append to your beancount file
bean-extract import_config.py ~/Downloads/cartola.xls >> accounts.beancount
```

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
├── beancount_chile/          # Main package
│   ├── __init__.py
│   ├── banco_chile.py        # Banco de Chile importer
│   ├── helpers.py            # Shared utilities
│   └── extractors/           # File format parsers
│       ├── __init__.py
│       └── banco_chile_xls.py
├── tests/                    # Test suite
│   ├── __init__.py
│   ├── test_banco_chile.py
│   └── fixtures/             # Test data (anonymized)
│       └── banco_chile_cartola_sample.xls
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
