# Architecture Overview

## High-Level Flow

```
┌─────────────┐
│   Gmail     │
│  API Call   │
└──────┬──────┘
       │ Search for MT940 emails
       │ (based on GMAIL_SEARCH_QUERY)
       ▼
┌─────────────────────┐
│  Gmail Client       │
│  - Authenticate     │
│  - Search emails    │
│  - Download files   │
└──────┬──────────────┘
       │ Extract .txt attachments
       ▼
┌──────────────────────┐
│ Attachment Processor │
│ - Parse content      │
│ - Validate format    │
└──────┬───────────────┘
       │ MT940 data
       ▼
┌──────────────────────┐
│  MT940 Parser        │
│ - Extract accounts   │
│ - Extract trans.     │
│ - Normalize data     │
└──────┬───────────────┘
       │ Structured data
       ▼
┌──────────────────────┐
│ Deduplication Check  │
│ - Content hash       │
│ - Filename check     │
└──────┬───────────────┘
       │ New transactions
       ▼
┌──────────────────────┐
│ Sheets Writer        │
│ - Format data        │
│ - Batch write        │
└──────┬───────────────┘
       │ (Optional) Matching
       │ (Optional) Transfer
       ▼
┌─────────────┐
│   Google    │
│   Sheets    │
│   API       │
└─────────────┘
```

## Component Architecture

### 1. Configuration Layer (`config/`)

**Responsibility:** Load and validate environment configuration.

**Key Classes:**
- `GmailSettings` — Gmail connection parameters
- `SheetsSettings` — Google Sheets access parameters
- `AppSettings` — Application behavior flags
- `load_settings()` — Entry point for configuration

**Features:**
- Pydantic-based validation
- Environment variable mapping
- Type-safe configuration
- Automatic directory creation for logs

### 2. Client Layer (`clients/`)

**Responsibility:** Abstract external API interactions.

#### GmailAuthenticator
- OAuth 2.0 flow management
- Token refresh and storage
- Credential management

#### GmailClient
- Email search and filtering
- Attachment download
- Label management
- Message archive operations

#### SheetsClient
- Spreadsheet access
- Sheet metadata queries
- Read/write operations
- Batch update support

### 3. Service Layer (`services/`)

**Responsibility:** Business logic and data processing.

#### AttachmentProcessor
- Extract file content from email attachments
- Validate file types (`.txt`)
- Handle encoding issues

#### SheetsWriter
- Format MT940 data for sheets
- Batch write transactions
- Handle sheet structure validation
- Append/update operations

#### Deduplication Services
- `DeduplicationService` — Content hash-based deduplication
- `SmartDeduplicationService` — Enhanced deduplication with archival
- `TransferMatchingService` — Matching with sequential numbering

#### Matching Services
- `MatchingService` — Basic text/type matching
- `MatchingUpdater` — Batch updates for matched data
- `TransferMatchingService` — Combined transfer + matching

#### Batch Operations
- `BatchWriter` — Efficient batch writes to sheets
- `BatchUpdater` — Efficient batch updates

### 4. Parser Layer (`parsers/`)

**Responsibility:** Parse structured data formats (MT940).

#### MT940Parser
- Parse MT940 bank statement format
- Extract transactions (`:61:` tags)
- Extract balances (`:60:`, `:62:` tags)
- Handle date/amount normalization
- Error handling and validation

**Key Methods:**
- `parse()` — Main entry point
- `_parse_opening_balance()` — Balance parsing
- `_parse_transactions()` — Transaction extraction
- `_parse_transaction_line()` — Single transaction parser
- `_parse_amount()` — Amount normalization
- `_format_date_mt940()` — Date format conversion

### 5. Models Layer (`models/`)

**Responsibility:** Data structures and type definitions.

#### Transaction
- Fields: account, date, description, amount, type, source
- Represents a single MT940 transaction
- Normalized form for sheets writing

#### MT940Header
- Opening and closing balances
- Date information
- Used for validation

#### MT940File
- Container for parsed MT940 data
- Headers + transaction list
- Metadata (source, processing timestamp)

### 6. Validators Layer (`validators/`)

**Responsibility:** Data validation and deduplication.

#### DeduplicationService
- Track processed transactions
- Filename and content hash comparison
- Prevent reprocessing

### 7. Exceptions Layer (`exceptions/`)

**Responsibility:** Application-specific exceptions.

**Key Exceptions:**
- `GmailToSheetsException` — Base exception
- `AuthenticationError` — Auth failures
- `MT940ParseError` — Parsing failures
- `DeduplicationError` — Duplicate detection

### 8. Orchestrator (`orchestrator.py`)

**Responsibility:** Coordinate the entire pipeline.

**Flow:**
1. Load configuration
2. Authenticate clients (Gmail + Sheets)
3. Search for emails
4. Process attachments
5. Write to sheets
6. (Optional) Transfer to CONTAORDEM
7. (Optional) Apply matching logic
8. Archive processed emails
9. Log results

## Data Flow

### Configuration Phase
```
.env file
    ↓
Pydantic validation
    ↓
AppSettings object (immutable during runtime)
```

### Email Processing Phase
```
Gmail API Search
    ↓
Message list
    ↓
Download attachments
    ↓
Parse .txt content
    ↓
MT940Parser
    ↓
Transaction objects
```

### Deduplication Phase
```
Transaction content
    ↓
Hash calculation (SHA256)
    ↓
Compare with existing
    ↓
Keep (new) or skip (duplicate)
```

### Sheets Write Phase
```
Filtered transactions
    ↓
Format for sheets
    ↓
Batch builder
    ↓
Sheets API batch write
    ↓
Update sheets metadata
```

### Optional Matching Phase
```
Source data (CONTAORDEM sheet)
    ↓
Reference data (CONSTANTES sheet)
    ↓
Text/Type/Value matching
    ↓
Sequential numbering per day
    ↓
Batch update both sheets
```

## Key Design Patterns

### 1. Dependency Injection
Services receive dependencies (clients, settings) in constructors.
Enables testing and loose coupling.

### 2. Configuration as Dependency
AppSettings injected into Orchestrator.
Allows different configurations for different environments.

### 3. Batch Processing
- Batch writes to sheets (reduced API calls)
- Configurable batch size
- Automatic batching in services

### 4. Idempotent Operations
- Deduplication prevents reprocessing
- Archive after write (state tracking)
- Safe to re-run without data corruption

### 5. Error Handling
- Custom exception hierarchy
- Logging at appropriate levels
- Graceful degradation

## Performance Considerations

### Batch Size Impact
- Larger batches = fewer API calls (faster)
- Smaller batches = lower memory usage
- Default: 100 (tunable via `BATCH_SIZE`)

### API Rate Limiting
- Google APIs have per-second quotas
- Batch writes reduce API calls significantly
- Implement backoff for 429 responses

### Memory Management
- All data loaded in memory during processing
- Large attachments may cause issues
- Consider streaming for very large files

## Security Considerations

### Credentials
- OAuth tokens stored locally (not in code)
- Service account JSON secured
- Credentials excluded from version control

### Data in Transit
- HTTPS for all API calls
- OAuth 2.0 for Gmail authentication
- Service account for Sheets access

### Data at Rest
- Credentials on disk must be secured (chmod 600)
- Logs may contain sensitive data (review before sharing)
- Archival emails left in Gmail (configure retention policy)

## Extension Points

### Adding New Data Sources
1. Create new client in `clients/`
2. Implement authentication
3. Add parser in `parsers/` if needed
4. Wire into orchestrator

### Adding New Output Formats
1. Create formatter in `services/`
2. Implement batch write logic
3. Add to orchestrator flow
4. Test with sample data

### Custom Matching Logic
1. Extend `MatchingService`
2. Override matching criteria
3. Configure in `.env`
4. Add tests

## Known Limitations

### Type Checking
- mypy reports 46 errors (known architectural issues)
- Gradual migration to proper type hints recommended
- Google libraries lack type stubs

### Module Duplication
- Fixed with `explicit_package_bases = true`
- Requires proper Python path handling

### Sequential Matching
- Operates per-day with numeric sequences
- Concurrent runs may cause sequence conflicts
- Single-threaded execution recommended

### File Size Limits
- Google API has file size limits
- Sheet row limits (1 million rows)
- Very large statements may need splitting

## Testing Strategy

### Unit Tests
- Configuration loading
- Data parsing (mock files)
- Utility functions

### Integration Tests
- Mock Google APIs
- Test end-to-end flow
- Verify data transformation

### Manual Testing
- Small email sample
- Verify sheet output
- Check deduplication
- Test archival

## Deployment Architecture

```
┌─────────────────────┐
│  Local Development  │
│   (Python 3.11)     │
└─────────────────────┘
           ↓
┌─────────────────────┐
│  CI/CD Pipeline     │
│  (Tests + Lint)     │
└─────────────────────┘
           ↓
┌─────────────────────┐
│  Remote Server      │
│  (Oracle Linux)     │
│  (Cron scheduled)   │
└─────────────────────┘
           ↓
┌─────────────────────┐
│  Gmail + Sheets     │
│  (APIs)             │
└─────────────────────┘
```

