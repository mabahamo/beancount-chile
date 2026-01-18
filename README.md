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

### Install

```bash
pip install beancount-chile
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
- **Custom categorization**: Optional categorizer function for automatic transaction categorization

## Advanced Features

### Custom Categorization

Both importers support an optional `categorizer` parameter that allows you to automatically categorize transactions by providing a custom function. This is more flexible than pattern matching approaches as it gives you full control over the categorization logic.

#### Categorizer Function Signature

```python
def categorizer(date, payee, narration, amount, metadata):
    """
    Categorize a transaction and optionally override payee/narration/subaccount.

    Args:
        date: Transaction date (datetime.date)
        payee: Extracted payee name (str)
        narration: Transaction description (str)
        amount: Transaction amount (Decimal, negative for debits)
        metadata: Dict with transaction-specific metadata

    Returns:
        Dict with optional fields (all fields are optional):
        - category: str - Single category account
        - payee: str - Override transaction payee
        - narration: str - Override transaction narration
        - subaccount: str - Subaccount suffix for main account
        - postings: List[Dict] - For splits, each with 'category' and 'amount' keys

        Or None for no categorization
    """
    # Your categorization logic here
    return {"category": "Expenses:Category"} or None
```

#### Metadata Available

**For Checking Account (BancoChileImporter):**
- `channel`: Transaction channel (e.g., "Internet", "Sucursal")
- `debit`: Debit amount (Decimal or None)
- `credit`: Credit amount (Decimal or None)
- `balance`: Account balance after transaction (Decimal)

**For Credit Card (BancoChileCreditImporter):**
- `statement_type`: "facturado" or "no_facturado"
- `installments`: Installment info (e.g., "01/12" or None)
- `category`: Transaction category for billed statements
- `city`: Transaction city for unbilled statements
- `card_type`: Card information for unbilled statements

#### Example: Simple Pattern Matching

```python
def my_categorizer(date, payee, narration, amount, metadata):
    """Categorize based on payee name patterns."""
    # Internet services
    if "Starlink" in payee or "STARLINK" in narration:
        return {"category": "Expenses:Internet"}

    # Transportation
    if any(keyword in narration.upper() for keyword in ["UBER", "CABIFY", "TAXI"]):
        return {"category": "Expenses:Transportation"}

    # Groceries
    if any(store in payee.upper() for store in ["JUMBO", "UNIMARC", "SANTA ISABEL"]):
        return {"category": "Expenses:Groceries"}

    # Don't categorize this transaction
    return None

CONFIG = [
    BancoChileImporter(
        account_number="00-123-45678-90",
        account_name="Assets:BancoChile:Checking",
        currency="CLP",
        categorizer=my_categorizer,
    ),
]
```

#### Example: Amount-Based Categorization

```python
def amount_based_categorizer(date, payee, narration, amount, metadata):
    """Categorize based on transaction amount."""
    # Large debits might be rent or major expenses
    if amount < -500000:  # More than 500k CLP debit
        return {"category": "Expenses:Major"}

    # Credits are income
    if amount > 0:
        return {"category": "Income:Salary"}

    return None
```

#### Example: Metadata-Based Categorization

```python
def metadata_categorizer(date, payee, narration, amount, metadata):
    """Categorize based on transaction metadata."""
    # Only categorize online transactions
    if metadata.get("channel") == "Internet":
        if amount < 0:  # Debit
            return {"category": "Expenses:Online"}

    # For credit cards, use statement type
    if metadata.get("statement_type") == "facturado":
        # Already billed transactions
        return {"category": "Expenses:CreditCard"}

    return None
```

#### Example: Different Categorizers for Different Accounts

```python
def checking_categorizer(date, payee, narration, amount, metadata):
    """Categorizer for checking account."""
    if "Starlink" in payee:
        return {"category": "Expenses:Internet"}
    return None

def credit_card_categorizer(date, payee, narration, amount, metadata):
    """Categorizer for credit card."""
    if "NETFLIX" in payee.upper():
        return {"category": "Expenses:Streaming"}
    if metadata.get("city") == "LAS CONDES":
        return {"category": "Expenses:Shopping"}
    return None

CONFIG = [
    BancoChileImporter(
        account_number="00-123-45678-90",
        account_name="Assets:BancoChile:Checking",
        currency="CLP",
        categorizer=checking_categorizer,
    ),
    BancoChileCreditImporter(
        card_last_four="1234",
        account_name="Liabilities:CreditCard:BancoChile",
        currency="CLP",
        categorizer=credit_card_categorizer,
    ),
]
```

#### Example: Transaction Splitting

The categorizer can return a dict with `postings` to split one transaction into multiple postings with fixed amounts. This is useful for:
- Splitting shared expenses across multiple categories
- Allocating specific amounts to different accounts
- Handling transactions with multiple components

```python
from decimal import Decimal

def split_categorizer(date, payee, narration, amount, metadata):
    """Split transactions into multiple fixed-amount postings."""
    # Split grocery shopping between food and household supplies
    if "JUMBO" in payee.upper() or "UNIMARC" in payee.upper():
        # For checking account, debits are negative
        if amount < 0:  # Debit
            return {
                "postings": [
                    {"category": "Expenses:Groceries", "amount": Decimal("40000")},
                    {"category": "Expenses:Household", "amount": Decimal("10000")},
                ]
            }

    # Split pharmacy purchase between medicine and personal care
    if "PHARMACY" in payee.upper():
        if amount < 0:
            return {
                "postings": [
                    {"category": "Expenses:Health:Medicine", "amount": Decimal("25000")},
                    {"category": "Expenses:Health:Personal", "amount": Decimal("8000")},
                ]
            }

    # For credit cards, amounts are positive (increase liability)
    # Split subscription service between personal and family
    if "NETFLIX" in payee.upper():
        return {
            "postings": [
                {"category": "Expenses:Streaming:Personal", "amount": Decimal("-6000")},
                {"category": "Expenses:Streaming:Family", "amount": Decimal("-6000")},
            ]
        }

    # No split needed
    return None

CONFIG = [
    BancoChileImporter(
        account_number="00-123-45678-90",
        account_name="Assets:BancoChile:Checking",
        currency="CLP",
        categorizer=split_categorizer,
    ),
]
```

**Important Notes on Transaction Splitting:**

1. **Amount Signs**:
   - For checking accounts: debits are negative, so split amounts should be positive
   - For credit cards: charges are positive, so split amounts should be negative
   - The split amounts balance the original transaction

2. **Balance**: The sum of split amounts should balance the original transaction amount. Beancount will flag unbalanced transactions.

3. **Flexible Splits**: You can split into any number of postings:
```python
# Split into 3 categories with fixed amounts
return {
    "postings": [
        {"category": "Expenses:Groceries", "amount": Decimal("30000")},
        {"category": "Expenses:Household", "amount": Decimal("15000")},
        {"category": "Expenses:Personal", "amount": Decimal("5000")},
    ]
}
```

4. **Mixed Amounts**: You can combine fixed amounts with calculated remainders:
```python
# Allocate fixed amount to one category, rest to another
if "PHARMACY" in payee.upper():
    medicine_amount = Decimal("15000")
    return {
        "postings": [
            {"category": "Expenses:Health:Medicine", "amount": medicine_amount},
            {"category": "Expenses:Health:Personal", "amount": -amount - medicine_amount},  # Remainder
        ]
    }
```

#### Example Output with Categorizer

**Single Posting (String Return):**

When a categorizer returns a single account string, transactions will have two postings:

```beancount
2026-01-01 * "Starlink" "Pago:starlink Starlink"
  channel: "Internet"
  Assets:BancoChile:Checking  -48000 CLP
  Expenses:Internet            48000 CLP

2026-01-16 ! "NETFLIX.COM" "NETFLIX.COM COMPRAS"
  statement_type: "no_facturado"
  city: "LAS CONDES"
  installments: "01/01"
  Liabilities:CreditCard:BancoChile  12000 CLP
  Expenses:Streaming                -12000 CLP
```

**Split Postings (List Return):**

When a categorizer returns a list of (account, amount) tuples, transactions can have multiple category postings:

```beancount
2026-01-15 * "Jumbo" "Supermercado Jumbo Santiago"
  channel: "Internet"
  Assets:BancoChile:Checking  -50000 CLP
  Expenses:Groceries           40000 CLP
  Expenses:Household           10000 CLP

2026-01-20 * "Restaurant Central" "Restaurant Central Santiago"
  channel: "Internet"
  Assets:BancoChile:Checking  -35000 CLP
  Expenses:Food:Restaurant     24500 CLP
  Expenses:Entertainment       10500 CLP

2026-01-16 ! "NETFLIX.COM" "NETFLIX.COM COMPRAS"
  statement_type: "no_facturado"
  city: "LAS CONDES"
  installments: "01/01"
  Liabilities:CreditCard:BancoChile  12000 CLP
  Expenses:Streaming:Personal        -6000 CLP
  Expenses:Streaming:Family          -6000 CLP
```

#### Best Practices

1. **Start Simple**: Begin with a few high-frequency patterns and expand over time
2. **Return None**: Always return `None` for transactions you don't want to categorize automatically
3. **Case Insensitive**: Use `.upper()` or `.lower()` for pattern matching to handle case variations
4. **Test Thoroughly**: Review categorized transactions to ensure accuracy
5. **Use Metadata**: Leverage the metadata dict for more precise categorization rules
6. **Combine Strategies**: Mix pattern matching, amount-based, and metadata-based logic as needed

### Virtual Subaccounts (NEW in v0.6.0)

The categorizer can specify subaccounts along with other fields using the dict-based API. This is perfect for envelope budgeting or tracking earmarked funds.

#### Subaccount Examples

**1. Subaccount + Category**
```python
def my_categorizer(date, payee, narration, amount, metadata):
    """Return dict with subaccount and category"""
    if "SHELL" in payee.upper() or "COPEC" in payee.upper():
        return {"subaccount": "Car", "category": "Expenses:Car:Gas"}
    return None

# Creates: Assets:BancoChile:Checking:Car -> Expenses:Car:Gas
```

**2. Subaccount + Split Postings**
```python
def my_categorizer(date, payee, narration, amount, metadata):
    """Return dict with subaccount and split postings"""
    if "JUMBO" in payee.upper():
        return {
            "subaccount": "Household",
            "postings": [
                {"category": "Expenses:Groceries", "amount": Decimal("40000")},
                {"category": "Expenses:Household", "amount": Decimal("10000")},
            ]
        }
    return None

# Creates: Assets:BancoChile:Checking:Household -> multiple expense accounts
```

**3. Subaccount Only (No Category)**
```python
def my_categorizer(date, payee, narration, amount, metadata):
    """Return dict with subaccount only"""
    # Large deposits go to emergency fund, but don't categorize
    if amount > 500000:
        return {"subaccount": "Emergency"}
    return None

# Creates: Assets:BancoChile:Checking:Emergency (single posting, no category)
```

**4. Payee & Narration Overrides**
```python
def my_categorizer(date, payee, narration, amount, metadata):
    """Return dict with payee and narration overrides"""
    if "CGE" in payee.upper():
        return {
            "payee": "CGE",
            "narration": "Electricity bill",
            "category": "Expenses:Utilities:Electricity"
        }
    return None

# Overrides payee and narration in the transaction
```

#### Example: Combining All Features

```python
from decimal import Decimal

def my_categorizer(date, payee, narration, amount, metadata):
    """Single function with all capabilities!"""
    # Subaccount + category
    if "SHELL" in payee.upper() or "COPEC" in payee.upper():
        return {"subaccount": "Car", "category": "Expenses:Car:Gas"}

    # Subaccount + split postings
    if "JUMBO" in payee.upper():
        return {
            "subaccount": "Household",
            "postings": [
                {"category": "Expenses:Groceries", "amount": Decimal("40000")},
                {"category": "Expenses:Household", "amount": Decimal("10000")},
            ]
        }

    # Subaccount only (no category)
    if amount > 500000:
        return {"subaccount": "Emergency"}

    # Just category (no subaccount)
    if "NETFLIX" in payee.upper():
        return {"category": "Expenses:Streaming"}

    # Payee override
    if "CGE" in narration.upper():
        return {
            "payee": "CGE",
            "narration": "Monthly electricity",
            "category": "Expenses:Utilities:Electricity"
        }

    return None  # No categorization

CONFIG = [
    BancoChileImporter(
        account_number="00-123-45678-90",
        account_name="Assets:BancoChile:Checking",
        currency="CLP",
        categorizer=my_categorizer,
    ),
]
```

#### Example Output

**Subaccount + Category:**
```beancount
2026-01-05 * "Shell" "Shell Costanera"
  channel: "Internet"
  Assets:BancoChile:Checking:Car  -45000 CLP
  Expenses:Car:Gas                 45000 CLP
```

**Subaccount + Split Postings:**
```beancount
2026-01-08 * "Jumbo" "Supermercado Jumbo"
  channel: "Internet"
  Assets:BancoChile:Checking:Household  -50000 CLP
  Expenses:Groceries                     40000 CLP
  Expenses:Household                     10000 CLP
```

**Subaccount Only:**
```beancount
2026-01-10 * "Salary Deposit" "Monthly Salary"
  channel: "Internet"
  Assets:BancoChile:Checking:Emergency  600000 CLP
```

#### Use Cases

- **Envelope Budgeting**: Track money earmarked for different purposes (Car, Vacation, Emergency)
- **Savings Goals**: Separate virtual accounts for different savings objectives
- **Business/Personal Separation**: Split credit card expenses by purpose
- **Budget Categories**: Map transactions to budget envelopes automatically

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
