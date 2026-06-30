# Invoice Processor — Architecture

Multi-agent invoice processing system built with LangGraph. Automates the full AP workflow: ingest → validate → approve → pay.

---

## State Machine

```
CLI: python main.py --invoice data/invoices/invoice_1001.txt
        │
        ▼
  ┌─────────────┐
  │  load_raw   │  Read file, detect format (pdf/txt/json/csv/xml)
  └──────┬──────┘
         │
         ▼
  ┌──────────────────────────────────────┐
  │  extract                             │
  │  • JSON/CSV/XML → deterministic      │
  │  • PDF/TXT → LLM structured output   │ ◄──┐
  │  • confidence < 0.7 → retry with     │    │ max 2 retries
  │    prior attempt in context          │────┘
  └──────┬───────────────────────────────┘
         │
         ▼
  ┌──────────────────────────────────────┐
  │  validate                            │
  │  Runs all checks, collects results:  │
  │  • query_inventory(item)             │
  │  • check_price_deviation(item,price) │
  │  • check_math(line_items)            │
  │  • check_duplicate(invoice_number)   │
  └──────┬───────────────────────────────┘
         │ critical issues?
         ├─────────────────────► reject → END
         │
         ▼
  ┌──────────────────────────────────────┐
  │  approve                             │
  │  • total < $10K  → standard check    │
  │  • total ≥ $10K  → heightened scrutiny
  │  LLM reasons → approved | rejected   │
  └──────┬───────────────────────────────┘
         │ rejected?
         ├─────────────────────► reject → END
         │
         ▼
  ┌─────────────┐
  │   payment   │  Mock transaction ID
  └──────┬──────┘  Write to processed_invoices
         │
         ▼
        END
```

---

## Agents

| Agent | LLM | Pattern | Self-correction |
|---|---|---|---|
| Ingestion | Yes | `with_structured_output(Invoice)` | Retry with prior attempt in context (max 2) |
| Validation | No | Sequential tool calls | None — deterministic |
| Approval | Yes | `with_structured_output(ApprovalDecision)` | None |
| Payment | No | Pure logic | None |

---

## Database Schema

```sql
-- Inventory with pricing (extended beyond minimum)
CREATE TABLE inventory (
    item_name     TEXT PRIMARY KEY,
    stock_qty     INTEGER NOT NULL,
    unit_price    REAL NOT NULL,
    category      TEXT,
    max_order_qty INTEGER
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
    processed_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Seed data:**
| Item | Stock | Unit Price | Category | Max Order |
|---|---|---|---|---|
| WidgetA | 15 | $250.00 | widget | 20 |
| WidgetB | 10 | $500.00 | widget | 15 |
| GadgetX | 5 | $750.00 | gadget | 10 |
| FakeItem | 0 | $0.00 | unknown | 0 |

---

## Validation Checks

1. **Item exists** — is the item in inventory?
2. **Stock available** — enough units in stock?
3. **Price deviation** — invoice unit price within 10% of contract price?
4. **Math correct** — do line item totals add up?
5. **Duplicate** — has this invoice number been processed before?

---

## Approval Rules

- **Auto-reject** if validation has critical issues
- **Standard approval** if total < $10,000 and no warnings
- **Heightened scrutiny** if total ≥ $10,000 — LLM reasons more carefully before deciding

---

## LLM Config

Priority: `XAI_API_KEY` (Grok) → `OPENAI_API_KEY` → `ANTHROPIC_API_KEY`

All backends use the same LangChain interface. Swap in `config.py`.

---

## File Structure

```
invoice-processor/
├── ARCHITECTURE.md
├── README.md
├── main.py                  # CLI: python main.py --invoice <path>
├── config.py                # LLM factory, thresholds
├── models/
│   ├── __init__.py
│   └── invoice.py           # Pydantic models + InvoiceState TypedDict
├── workflow/
│   ├── __init__.py
│   └── graph.py             # LangGraph StateGraph
├── agents/
│   ├── __init__.py
│   ├── ingestion.py         # extract + self-correction retry
│   ├── validation.py        # sequential tool calls
│   ├── approval.py          # rules + LLM decision
│   └── payment.py           # mock payment logic
├── tools/
│   ├── __init__.py
│   ├── parsers.py           # pdf / txt / json / csv / xml
│   └── inventory_db.py      # SQLite setup, seed, tool functions
├── data/
│   └── invoices/            # 16 sample invoices (all formats)
├── .env.example
└── requirements.txt
```

---

## Sample Run

```
$ python main.py --invoice data/invoices/invoice_1001.txt

Processing: invoice_1001.txt
  [load]     format=txt
  [extract]  INV-1001 | Widgets Inc. | $5,000.00 | confidence=0.97
  [validate] ✓ all items in inventory | ✓ math correct | ✓ no duplicate
  [approve]  APPROVED — standard check, total under threshold
  [payment]  transaction_id=TXN-20260629-A3F2 | amount=$5,000.00

Result: APPROVED | $5,000.00 | TXN-20260629-A3F2
```
