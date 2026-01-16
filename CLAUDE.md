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

- ✅ **Banco de Chile** - XLS/XLSX cartola (account statements)

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

## Future Improvements

- [ ] Add PDF parsing support for banks that only provide PDF statements
- [ ] Implement CSV importers for banks with CSV exports
- [ ] Add support for credit card statements
- [ ] Implement automatic payee categorization
- [ ] Add CLI tool for easier usage
- [ ] Create web interface for non-technical users
- [ ] Add support for investment account statements

## References

- [Beancount Documentation](https://beancount.github.io/docs/)
- [Beangulp Documentation](https://github.com/beancount/beangulp)
- [beancount-dkb](https://github.com/siddhantgoel/beancount-dkb) - Reference implementation
