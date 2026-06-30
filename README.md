# Automated Invoice Processor

A multi-agent AI system that automates Acme Corp's end-to-end invoice workflow: ingest → validate → approve → pay.

**Business problem:** Acme Corp loses $2M/year to manual invoice processing — 30% error rate, 5-day delays, and staff bottlenecks. This system replaces that workflow with a LangGraph-orchestrated multi-agent pipeline that processes invoices in seconds.

---

## How It Works

Four specialized agents run in sequence, each with a single responsibility:

| Agent | What it does |
|---|---|
| **Ingestion** | Parses any invoice format (PDF, TXT, JSON, CSV, XML) into structured data. Uses LLM extraction for unstructured formats with a self-correction retry loop. |
| **Validation** | Checks each line item against inventory: item exists, stock available, price within 10% of contract, math correct, no duplicate invoice. |
| **Approval** | Applies business rules — standard check under $10K, heightened LLM scrutiny at $10K+. Returns approved or rejected with reasoning. |
| **Payment** | Executes mock payment for approved invoices, logs rejections. All outcomes written to audit table. |

### Self-correction loop (Ingestion)

For messy PDFs and typo-ridden text invoices, the LLM assigns a confidence score on extraction. If confidence < 0.70, the agent re-prompts with the original text and its prior attempt, giving it a chance to correct itself (max 2 retries).

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure your LLM

Copy `.env.example` to `.env` and add your API key:

```bash
cp .env.example .env
```

```
# Priority: OpenAI → Grok → Claude
OPENAI_API_KEY=sk-...
```

### 3. Run

```bash
# Process a single invoice
python main.py --invoice data/invoices/invoice_1001.txt

# View processing history
python main.py --history
```

The SQLite database (`data/invoice_processor.db`) is created automatically on first run.

---

## Supported Formats

| Format | Parsing method |
|---|---|
| `.json` | Deterministic — no LLM needed |
| `.csv` | Deterministic — handles both key-value and tabular layouts |
| `.xml` | Deterministic — no LLM needed |
| `.txt` | LLM extraction with self-correction |
| `.pdf` | pdfplumber text extraction → LLM extraction with self-correction |

---

## Validation Checks

1. **Duplicate invoice** — rejects if the invoice number was already processed (prevents double payment)
2. **Item exists** — rejects if any line item is not in inventory
3. **Stock available** — rejects if requested quantity exceeds stock
4. **Price deviation** — warns if unit price deviates >10% from contract price (extended from base schema)
5. **Math correct** — rejects if line item totals don't add up

---

## Database Schema

```sql
-- Base inventory (extended with unit_price for price validation)
CREATE TABLE inventory (
    item       TEXT PRIMARY KEY,
    stock      INTEGER NOT NULL,
    unit_price REAL NOT NULL
);

-- Audit trail + duplicate detection
CREATE TABLE processed_invoices (
    invoice_number TEXT PRIMARY KEY,
    vendor         TEXT,
    total          REAL,
    currency       TEXT,
    decision       TEXT,
    reasoning      TEXT,
    transaction_id TEXT,
    processed_at   TEXT
);
```

**Seed data:**

| Item | Stock | Contract Price |
|---|---|---|
| WidgetA | 15 | $250.00 |
| WidgetB | 10 | $500.00 |
| GadgetX | 5 | $750.00 |
| FakeItem | 0 | $0.00 |

---

## Example Output

```
════════════════════════════════════════════════════════════
  ACME CORP — Invoice Processor
════════════════════════════════════════════════════════════
  File: data/invoices/invoice_1001.txt
────────────────────────────────────────────────────────────
  [mock bank] POST /payments → TXN-20260629-A3F2 | INV-1001 | USD 5,000.00
  Invoice:  INV-1001
  Vendor:   Widgets Inc.
  Total:    USD 5,000.00
  Confidence: 100%
────────────────────────────────────────────────────────────
  DECISION:  APPROVED
  REASONING: Invoice is legitimate — known items at correct prices, math checks out, under $10K threshold.
  TRANSACTION ID: TXN-20260629-A3F2
════════════════════════════════════════════════════════════
```

---

## Project Structure

```
invoice-processor/
├── main.py                  # CLI entry point
├── config.py                # LLM factory + thresholds
├── models/invoice.py        # Pydantic models + LangGraph state
├── workflow/graph.py        # LangGraph StateGraph
├── agents/
│   ├── ingestion.py         # Extract + self-correction retry
│   ├── validation.py        # Sequential validation checks
│   ├── approval.py          # Rules + LLM approval decision
│   └── payment.py           # Mock payment + audit logging
├── tools/
│   ├── parsers.py           # Multi-format parsers
│   └── inventory_db.py      # SQLite setup, seed, tool functions
└── data/
    └── invoices/            # 20 sample invoices (all formats)
```

---

## Design Decisions

**Why LangGraph?** State flows explicitly through typed nodes with conditional edges — easy to inspect, extend, and debug. Each agent is isolated and testable independently.

**Why deterministic parsing for JSON/CSV/XML?** LLMs are not needed when the data is already structured. Deterministic parsing is faster, cheaper, and more reliable. LLM extraction is reserved for genuinely unstructured input.

**Why a self-correction loop only in ingestion?** Validation and approval are deterministic or rule-driven — retrying them doesn't improve outcomes. Ingestion is where ambiguity lives (OCR artifacts, typos, inconsistent formatting), so that's where self-correction adds real value.
