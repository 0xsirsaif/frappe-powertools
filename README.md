# Frappe Powertools

[![GitHub](https://img.shields.io/badge/GitHub-Repository-181717?style=flat-square&logo=github)](https://github.com/0xsirsaif/frappe-powertools)

⚠️ BETA VERSION

## Workbook Validation

The `workbook` module provides Pydantic-powered validation for CSV and XLSX file uploads. It's designed to be a preflight check that validates tabular data before saving to the database.

### Features

- **Pydantic-powered validation**: Use Pydantic models as schemas for row validation
- **CSV and XLSX support**: Automatically detect or explicitly specify file format
- **Streaming processing**: Process files row-by-row without loading entire sheets into memory
- **Comprehensive error reporting**: Collect all validation errors before preventing saves
- **Frappe integration**: Convenient adapter for working with Frappe File documents

### Quick Start

#### 1. Define a Row Model

Create a Pydantic model that represents a single row in your workbook:

```python
from pydantic import BaseModel, EmailStr

class CustomerRow(BaseModel):
    code: str
    name: str
    email: EmailStr | None = None
    age: int | None = None
```

#### 2. Validate a Workbook

Use `validate_workbook` to validate an entire file:

```python
import io
from frappe_powertools.workbook.core import WorkbookConfig, validate_workbook

# For CSV files
csv_content = b"code,name,email\nCUST001,Alice,alice@example.com\nCUST002,Bob,bob@example.com"
fp = io.BytesIO(csv_content)

config = WorkbookConfig(format="auto", extra="ignore")
result = validate_workbook(fp, CustomerRow, config=config, file_name="customers.csv")

# Inspect results
print(f"Total rows: {result.summary.total_rows}")
print(f"Valid rows: {result.summary.valid_rows}")
print(f"Invalid rows: {result.summary.invalid_rows}")

# Get all valid models
valid_customers = result.valid_models

# Get all errors
for row_index, error in result.errors:
    print(f"Row {row_index}: {error}")
```

#### 3. Stream Validation (for Large Files)

For large files, use `iter_validated_rows` to process row-by-row:

```python
from frappe_powertools.workbook.core import iter_validated_rows

for row_result in iter_validated_rows(fp, CustomerRow, config=config):
    if row_result.is_valid:
        # Process valid row
        customer = row_result.model
        print(f"Processing {customer.code}")
    else:
        # Handle validation error
        print(f"Row {row_result.context.row_index} has errors: {row_result.error}")
```

#### 4. Using with Frappe File Documents

The Frappe adapter makes it easy to validate files stored in Frappe:

```python
from frappe_powertools.workbook.frappe import validate_file

# Validate a file by name
file_doc_name = "abc123def456"
result = validate_file(file_doc_name, CustomerRow)

# Or pass a File document instance
file_doc = frappe.get_doc("File", file_doc_name)
result = validate_file(file_doc, CustomerRow)

# Use custom configuration
config = WorkbookConfig(format="auto", max_rows=100)
result = validate_file(file_doc_name, CustomerRow, config=config)
```

### Configuration Options

The `WorkbookConfig` class provides various options for controlling validation:

```python
from frappe_powertools.workbook.core import WorkbookConfig, TabularFormat

config = WorkbookConfig(
    format=TabularFormat.auto,  # or "csv", "xlsx", "auto"
    header_row=1,                # 1-based row index for headers
    data_row_start=2,            # 1-based row index where data starts
    delimiter=",",               # CSV delimiter (default: ",")
    sheet_name=None,             # XLSX sheet name (None = active sheet)
    extra="ignore",              # "ignore", "forbid", or "allow"
    stop_on_first_error=False,   # Stop after first validation error
    max_rows=None,               # Maximum number of rows to process
)
```

### Format Auto-Detection

The validator can automatically detect file format:

- **From filename**: Uses file extension (`.csv`, `.xlsx`, `.xlsm`)
- **From content**: For binary streams, detects ZIP magic bytes (XLSX files are ZIP archives)
- **From stream type**: TextIO streams are treated as CSV

```python
# Auto-detection from filename
result = validate_workbook(fp, CustomerRow, file_name="data.xlsx")

# Auto-detection from content (no filename)
result = validate_workbook(fp, CustomerRow)  # Will detect from stream type/magic bytes
```

### Error Handling

Validation errors are collected and returned in the result:

```python
result = validate_workbook(fp, CustomerRow, config=config)

if result.summary.invalid_rows > 0:
    print(f"Found {result.summary.invalid_rows} invalid rows")
    
    for row_index, error in result.errors:
        print(f"\nRow {row_index} errors:")
        for err in error.errors():
            print(f"  - {err['type']}: {err['msg']}")
            print(f"    Location: {err.get('loc', [])}")
```

### Advanced Usage

#### Custom Pydantic Models with Validation

You can use any Pydantic features in your models:

```python
from pydantic import BaseModel, EmailStr, Field, validator

class CustomerRow(BaseModel):
    code: str = Field(min_length=3, max_length=20)
    name: str = Field(min_length=1)
    email: EmailStr | None = None
    age: int | None = Field(None, ge=0, le=150)
    
    @validator('code')
    def code_must_be_uppercase(cls, v):
        return v.upper()
```

#### Handling Extra Columns

Control how extra columns are handled:

```python
# Ignore extra columns (default)
config = WorkbookConfig(extra="ignore")

# Forbid extra columns (raise error if extra columns exist)
config = WorkbookConfig(extra="forbid")

# Allow extra columns (include in validated model if model allows)
config = WorkbookConfig(extra="allow")
```

#### Limiting Rows Processed

For testing or preview purposes:

```python
# Process only first 10 rows
config = WorkbookConfig(max_rows=10)
result = validate_workbook(fp, CustomerRow, config=config)
```

#### Stopping on First Error

For quick validation checks:

```python
config = WorkbookConfig(stop_on_first_error=True)
result = validate_workbook(fp, CustomerRow, config=config)
```

### API Reference

#### Core Functions

- `iter_validated_rows(fp, model, *, config=None, file_name=None)`: Iterator that yields `RowResult` for each row
- `validate_workbook(fp, model, *, config=None, file_name=None)`: Collects all results and returns `WorkbookValidationResult`

#### Data Classes

- `WorkbookConfig`: Configuration for parsing and validation
- `RowContext`: Metadata and raw data for a single row
- `RowResult[TModel]`: Result of validating a single row
- `WorkbookSummary`: Summary statistics (total, valid, invalid rows)
- `WorkbookValidationResult[TModel]`: Complete validation result

#### Frappe Adapter

- `validate_file(file, model, *, config=None, background=None, job_name=None)`: Validate a Frappe File document

### Examples

See the test files for more examples:

- `tests/workbook/test_csv.py`: CSV validation examples
- `tests/workbook/test_xlsx.py`: XLSX validation examples
- `tests/workbook/test_frappe.py`: Frappe adapter examples
