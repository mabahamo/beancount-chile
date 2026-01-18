# CLAUDE.md - Project Context for beancount-chile

This document contains important context and conventions for developing the beancount-chile project.

## Project Overview

**beancount-chile** is a collection of Beancount importers for Chilean banks. The project uses the beangulp framework to provide standardized importers that convert bank statement files into Beancount double-entry bookkeeping entries.

### Goals

- Support major Chilean banks (Banco de Chile, Banco Estado, Santander, BCI, etc.)
- Handle multiple file formats (XLS, XLSX, PDF, CSV)
- Provide robust, well-tested importers
- Maintain privacy by never committing real banking data
- Follow Beancount 3.x conventions

## Architecture

### Core Components

1. **Importers** (`beancount_chile/*.py`)
   - Main importer classes that implement `beangulp.Importer`
   - Named after the bank: `banco_chile.py`, `banco_estado.py`, etc.
   - Export from `__init__.py` for easy access

2. **Extractors** (`beancount_chile/extractors/*.py`)
   - File format parsers (XLS, PDF, CSV, etc.)
   - Extract structured data from various file formats
   - Return dataclasses with metadata and transactions
   - Named by bank and format: `banco_chile_xls.py`, `banco_estado_pdf.py`

3. **Helpers** (`beancount_chile/helpers.py`)
   - Shared utility functions
   - Payee normalization
   - Amount parsing
   - Date handling

4. **Tests** (`tests/`)
   - Comprehensive test coverage for all importers
   - Use anonymized fixtures in `tests/fixtures/`
   - Test both extractors and importers separately

### Importer Interface

All importers must implement these beangulp.Importer methods:

```python
class BankImporter(Importer):
    def identify(self, filepath: Path) -> bool:
        """Check if this file can be processed."""
        pass

    def account(self, filepath: Path) -> str:
        """Return the account name."""
        pass

    def date(self, filepath: Path) -> Optional[datetime]:
        """Extract the statement date."""
        pass

    def filename(self, filepath: Path) -> Optional[str]:
        """Generate standardized filename."""
        pass

    def extract(self, filepath: Path, existing: Optional[data.Entries] = None) -> data.Entries:
        """Extract Beancount entries."""
        pass
```

### Data Flow

1. **Input**: Bank statement file (XLS, PDF, CSV, etc.)
2. **Extractor**: Parses file → Returns (Metadata, Transactions)
3. **Importer**: Converts Transactions → Beancount Entries
4. **Output**: Beancount journal entries

## Conventions

### Code Style

- Follow PEP 8
- Use type hints for all function signatures
- Use dataclasses for structured data
- Use `ruff` for linting and formatting
- Maximum line length: 88 characters

### Naming

- Importers: `BancoNameImporter` (e.g., `BancoChileImporter`)
- Extractors: `BancoNameFormatExtractor` (e.g., `BancoChileXLSExtractor`)
- Test files: `test_banco_name.py`
- Fixtures: `banco_name_format_sample.ext`

### Testing

- Every importer MUST have comprehensive tests
- Test both the extractor and importer separately
- Use pytest for all tests
- Aim for >90% code coverage
- Test edge cases: empty files, malformed data, missing fields

### Privacy and Security

**CRITICAL**: Never commit real banking data

- All test fixtures must use anonymized data
- Mock names: "Juan Pérez González", "María González", etc.
- Mock RUTs: "12.345.678-9", "98.765.432-1"
- Mock account numbers: "00-123-45678-90"
- Realistic but fake transaction descriptions
- `.gitignore` excludes `*.xls`, `*.xlsx`, `*.pdf` (except `tests/fixtures/`)

### Git Workflow

- Never commit directly to `main`
- Create feature branches: `feature/banco-name-format-importer`
- Write descriptive commit messages
- Run tests before committing
- Update README.md and CLAUDE.md with changes

## Supported Banks (Current & Planned)

### Implemented

- ✅ **Banco de Chile** - XLS/XLSX/PDF cartola (account statements)
- ✅ **Banco de Chile** - XLS/XLSX credit card statements (Facturado/No Facturado)

### Planned

- 🔄 Banco Estado - PDF/XLS
- 🔄 Banco Santander - PDF/XLS
- 🔄 BCI - PDF/XLS
- 🔄 Banco Scotiabank - PDF/XLS
- 🔄 Banco Itaú - PDF/XLS
- 🔄 Banco Security - PDF/XLS

## File Format Patterns

### Banco de Chile XLS Format

Structure:
```
Rows 1-5:   Empty
Row 6:      Sr(a): [Name]
Row 7:      Rut: [RUT]
Row 8:      Cuenta: [Account Number]
Row 10:     Moneda: [Currency]
Row 16:     Balance headers
Row 17:     Balance values
Row 20:     Totals headers
Row 21:     Totals values
Row 25:     "Movimientos al [Date]"
Row 26:     Transaction headers
Row 27+:    Transactions
```

Columns:
- B: Fecha (Date)
- C: Descripción (Description)
- D: Canal o Sucursal (Channel/Branch)
- E: Cargos (Debits)
- F: Abonos (Credits)
- G: Saldo (Balance)

### Banco de Chile Credit Card XLS Format

**Facturado (Billed) Structure:**
```
Rows 1-7:   Empty
Row 8:      Sr(a).: [Name]
Row 9:      Rut: [RUT]
Row 10:     Tipo de Tarjeta: [Card Type with last 4 digits]
Row 11:     Estado: [Status]
Row 13:     "Movimientos Facturados"
Row 14:     Billing summary headers
Row 15:     Billing summary values (total, minimum payment, dates)
Row 17:     "Movimientos Nacionales"
Row 18:     Transaction headers
Row 19+:    Transactions
```

Facturado Columns:
- B: Categoría (Category)
- C: Fecha (Date)
- D: Descripción (Description)
- G: Cuotas (Installments)
- H: Monto (Amount)

**No Facturado (Unbilled) Structure:**
```
Rows 1-7:   Empty
Row 8:      Sr(a).: [Name]
Row 9:      Rut: [RUT]
Row 10:     Tipo de Tarjeta: [Card Type with last 4 digits]
Row 11:     Estado: [Status]
Row 13:     "Saldos y Movimientos No Facturados al [Date]"
Row 14:     Credit limit headers
Row 15:     Credit limit values (available, used, total)
Row 17:     "Movimientos Nacionales"
Row 18:     Transaction headers
Row 19+:    Transactions
```

No Facturado Columns:
- B: Fecha (Date)
- C: Tipo de Tarjeta (Card Type)
- E: Descripción (Description)
- G: Ciudad (City)
- H: Cuotas (Installments)
- K: Monto (Amount)

**Key Differences:**
- Facturado includes billing summary (total due, minimum payment, due date)
- No Facturado includes credit limit information
- Column layout differs between the two types
- Facturado transactions are marked as cleared (*), No Facturado as pending (!)

### Banco de Chile PDF Format (Cartola)

PDF cartola statements contain the same information as XLS files but require text extraction and parsing.

**PDF Structure:**
```
Header section (varies by page):
  - BANCO DE CHILE
  - CARTOLA N° : [number]
  - N° DE CUENTA : [account number]
  - Sr(a). : [Name]
  - RUT : [RUT]
  - DESDE : DD/MM/YYYY HASTA : DD/MM/YYYY
  - SALDO INICIAL [amount]

Transaction section:
  DD/MM DESCRIPTION [DETAILS] [AMOUNT] [BALANCE]

Footer section:
  SALDO FINAL [amount]
```

**Transaction Line Formats:**

1. **Standard Transfer (Debit)**:
   ```
   10/01 TRASPASO A:TEST USUARIO UNO INTERNET 3.147.734 12.100.583
   ```
   - Date: 10/01
   - Description: TRASPASO A:TEST USUARIO UNO INTERNET
   - Amount: 3.147.734 (debit)
   - Balance: 12.100.583

2. **Standard Transfer (Credit)**:
   ```
   02/01 TRASPASO DE:TEST USUARIO DOS INTERNET 75.000 100.000
   ```
   - Date: 02/01
   - Description: TRASPASO DE:TEST USUARIO DOS INTERNET
   - Amount: 75.000 (credit)
   - Balance: 100.000

3. **Check Deposit**:
   ```
   19/12 DEP.CHEQ.OTROS BANCOS OF. SAN PABLO 06545793 500.000 39.007.190
   ```
   - Date: 19/12
   - Description: DEP.CHEQ.OTROS BANCOS
   - Check number: 06545793 (8 digits)
   - Amount: 500.000 (credit)
   - Balance: 39.007.190

4. **Check Returned**:
   ```
   20/12 CHEQUE DEPOSITADO DEVUELTO OF. SAN PABLO 06545793 500.000 38.507.190
   ```
   - Date: 20/12
   - Description: CHEQUE DEPOSITADO DEVUELTO
   - Check number: 06545793 (8 digits)
   - Amount: 500.000 (debit)
   - Balance: 38.507.190

5. **PAGO Transaction with Folio**:
   ```
   15/01 PAGO:PROVEEDORES 0776016489 200.000 5.000.000
   ```
   - Date: 15/01
   - Description: PAGO:PROVEEDORES
   - Folio: 0776016489 (10 digits starting with 0)
   - Amount: 200.000 (credit)
   - Balance: 5.000.000

**Parsing Challenges:**

1. **Text Extraction**: PDF text needs to be extracted and split into lines
2. **Amount Format**: Chilean format uses dots as thousand separators (1.234.567)
3. **Date Format**: Transactions use DD/MM (year inferred from statement period)
4. **Transaction Type Detection**: Must identify credit vs debit based on keywords:
   - Credits (ingresos): "TRASPASO DE", "DEP.CHEQ", "REVERSO", "PAGO:PROVEEDORES", "Devolucion"
   - Debits (egresos): "TRASPASO A", "CHEQUE DEPOSITADO DEVUELTO", most other transactions
5. **Special Numbers**: Folio numbers (10 digits, start with 0) must be distinguished from amounts
6. **Variable Columns**: Amount and balance positions vary based on description length

**Implementation Notes:**

- Uses `pdfplumber` library for text extraction
- Regex patterns match transaction lines starting with DD/MM
- Special handling for check deposits/returns (8-digit check numbers)
- PAGO transactions with folios require filtering 10-digit numbers from amounts
- Lines are stripped of leading/trailing whitespace before parsing
- No channel information in PDF (unlike XLS which has "Canal o Sucursal" column)

## Adding a New Bank

### Step-by-Step Guide

1. **Create feature branch**
   ```bash
   git checkout -b feature/banco-name-format-importer
   ```

2. **Analyze the file format**
   - Download a real statement
   - Analyze structure (headers, columns, metadata location)
   - Document the format in this file

3. **Create anonymized test fixture**
   - Never use real data
   - Create `tests/fixtures/banco_name_format_sample.ext`
   - Include realistic but fake data

4. **Implement extractor**
   - Create `beancount_chile/extractors/banco_name_format.py`
   - Define dataclasses for Metadata and Transaction
   - Implement extraction logic
   - Add to `extractors/__init__.py`

5. **Implement importer**
   - Create `beancount_chile/banco_name.py`
   - Inherit from `beangulp.Importer`
   - Implement all required methods
   - Add to `__init__.py`

6. **Write tests**
   - Create `tests/test_banco_name.py`
   - Test extractor separately
   - Test importer separately
   - Test edge cases

7. **Run tests**
   ```bash
   pytest tests/test_banco_name.py -v
   ```

8. **Update documentation**
   - Add bank to README.md supported list
   - Document file format in CLAUDE.md
   - Add usage example to README.md

9. **Commit and push**
   ```bash
   git add .
   git commit -m "Add support for Banco Name FORMAT files"
   git push -u origin feature/banco-name-format-importer
   ```

## Common Issues and Solutions

### Issue: Excel file won't parse

**Solution**: Check file extension. Old `.xls` files need `xlrd` engine, newer `.xlsx` files use `openpyxl`.

```python
# For .xls
pd.read_excel(filepath, engine='xlrd')

# For .xlsx
pd.read_excel(filepath, engine='openpyxl')
```

### Issue: Dates not parsing correctly

**Solution**: Chilean date format is typically DD/MM/YYYY. Use:

```python
datetime.strptime(date_str, "%d/%m/%Y")
```

### Issue: Amounts have wrong decimal places

**Solution**: Chilean pesos (CLP) have no decimal places. Use:

```python
Decimal(str(int(value)))
```

### Issue: Test fixtures rejected by git

**Solution**: Check `.gitignore`. Test fixtures in `tests/fixtures/` should be allowed:

```gitignore
*.xls
*.xlsx
!tests/fixtures/*.xls
!tests/fixtures/*.xlsx
```

## Dependencies

### Production

- **beancount** (≥3.0.0): Core accounting library
- **beangulp** (≥0.1.1, <0.3.0): Import framework
- **pandas** (≥2.0.0): Data manipulation
- **openpyxl** (≥3.0.0): XLSX file support
- **xlrd** (≥2.0.0): XLS file support
- **pdfplumber** (≥0.10.0): PDF text extraction

### Development

- **pytest** (≥8.0.0): Testing framework
- **ruff** (≥0.5.0): Linting and formatting

## Development Environment

```bash
# Create venv
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Format code
ruff format .

# Lint code
ruff check .
```

## Version Support

- **Python**: 3.10, 3.11, 3.12, 3.13
- **Beancount**: 3.x only (no support for 2.x)
- **OS**: macOS, Linux, Windows

## Advanced Features

### Categorizer Tuple Returns (v0.5.0)

Starting in v0.5.0, categorizers can return tuples to specify both the subaccount suffix and the category in a single function. This provides a unified way to handle virtual subaccounts for envelope budgeting or tracking earmarked funds.

**Type Alias:**
```python
CategorizerReturn = Optional[
    Union[
        str,                                      # Single category (backward compatible)
        List[Tuple[str, Decimal]],                # Split postings (backward compatible)
        Tuple[str, str],                          # (subaccount_suffix, category_account) - NEW!
        Tuple[str, List[Tuple[str, Decimal]]],    # (subaccount_suffix, split_postings) - NEW!
        Tuple[str, None],                         # (subaccount_suffix, None) - Subaccount only - NEW!
    ]
]
```

**Return Types:**

1. **Simple Tuple**: `Tuple[str, str]`
   - First element: Subaccount suffix (e.g., "Car", "Household")
   - Second element: Category account (e.g., "Expenses:Car:Gas")
   ```python
   def categorizer(date, payee, narration, amount, metadata):
       if "SHELL" in payee.upper():
           return ("Car", "Expenses:Car:Gas")  # Tuple!
       return None
   ```
   Result: `Assets:BancoChile:Checking:Car` → `Expenses:Car:Gas`

2. **Tuple with Split Postings**: `Tuple[str, List[Tuple[str, Decimal]]]`
   - First element: Subaccount suffix
   - Second element: List of (account, amount) pairs for split postings
   ```python
   def categorizer(date, payee, narration, amount, metadata):
       if "JUMBO" in payee.upper():
           return ("Household", [
               ("Expenses:Groceries", -amount * Decimal("0.6")),
               ("Expenses:Household", -amount * Decimal("0.4")),
           ])
       return None
   ```
   Result: `Assets:BancoChile:Checking:Household` → split across multiple expense accounts

3. **Subaccount Only**: `Tuple[str, None]`
   - First element: Subaccount suffix
   - Second element: None (no automatic categorization)
   ```python
   def categorizer(date, payee, narration, amount, metadata):
       # Large deposits to emergency fund, but don't categorize
       if amount > 500000:
           return ("Emergency", None)
       return None
   ```
   Result: `Assets:BancoChile:Checking:Emergency` → single posting, no category added

**Implementation Details:**

The importer detects tuple returns with runtime type checking:
```python
# In _create_transaction_entry:
category_result = None
categorizer_subaccount = None

if self.categorizer:
    raw_result = self.categorizer(...)

    # Check if categorizer returned a tuple with (subaccount, category/splits/None)
    if isinstance(raw_result, tuple) and len(raw_result) == 2:
        categorizer_subaccount, category_result = raw_result
    else:
        category_result = raw_result

# Apply subaccount suffix if provided
if categorizer_subaccount:
    account_name = f"{self.account_name}:{categorizer_subaccount}"
else:
    account_name = self.account_name
```

**Backward Compatibility:**

All existing categorizers continue to work unchanged:
- Returning `None` → No categorization
- Returning `str` → Single category account
- Returning `List[Tuple[str, Decimal]]` → Split postings

**Use Cases:**

| Scenario | Return Type | Example |
|----------|-------------|---------|
| Simple expense categorization | `str` | `"Expenses:Groceries"` |
| Split postings across categories | `List[Tuple[str, Decimal]]` | `[("Expenses:A", 100), ("Expenses:B", 50)]` |
| Subaccount + category | `Tuple[str, str]` | `("Car", "Expenses:Car:Gas")` |
| Subaccount + split postings | `Tuple[str, List[...]]` | `("Household", [(account, amount), ...])` |
| Subaccount only (no category) | `Tuple[str, None]` | `("Emergency", None)` |

**Example: Complete Categorizer with All Return Types**

```python
from decimal import Decimal

def my_categorizer(date, payee, narration, amount, metadata):
    """Complete example showing all return types."""
    # Subaccount + category
    if "SHELL" in payee.upper():
        return ("Car", "Expenses:Car:Gas")

    # Subaccount + split postings
    if "JUMBO" in payee.upper():
        return ("Household", [
            ("Expenses:Groceries", Decimal("40000")),
            ("Expenses:Household", Decimal("10000")),
        ])

    # Subaccount only (no category)
    if amount > 500000:
        return ("Emergency", None)

    # Just category (no subaccount) - backward compatible
    if "NETFLIX" in payee.upper():
        return "Expenses:Streaming"

    # Split without subaccount - backward compatible
    if "PHARMACY" in payee.upper():
        return [
            ("Expenses:Health:Medicine", Decimal("15000")),
            ("Expenses:Health:Personal", -amount - Decimal("15000")),
        ]

    # No categorization
    return None

importer = BancoChileImporter(
    account_number="...",
    account_name="Assets:BancoChile:Checking",
    categorizer=my_categorizer,
)
```

## Future Improvements

- [x] Add PDF parsing support for banks that only provide PDF statements (Banco de Chile done)
- [ ] Implement CSV importers for banks with CSV exports
- [x] Add support for credit card statements (Banco de Chile done)
- [ ] Implement automatic payee categorization
- [ ] Add CLI tool for easier usage
- [ ] Create web interface for non-technical users
- [ ] Add support for investment account statements

## References

- [Beancount Documentation](https://beancount.github.io/docs/)
- [Beangulp Documentation](https://github.com/beancount/beangulp)
- [beancount-dkb](https://github.com/siddhantgoel/beancount-dkb) - Reference implementation
