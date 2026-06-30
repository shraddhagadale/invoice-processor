"""SQLite inventory DB — setup, seed data, and tool functions used by the validation agent."""

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional
from config import DB_PATH, PRICE_DEVIATION_PCT


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def setup_database() -> None:
    """Create tables and seed inventory if not already present."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS inventory (
                item       TEXT PRIMARY KEY,
                stock      INTEGER NOT NULL,
                unit_price REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS processed_invoices (
                invoice_number TEXT PRIMARY KEY,
                vendor         TEXT,
                total          REAL,
                currency       TEXT,
                decision       TEXT,
                reasoning      TEXT,
                transaction_id TEXT,
                processed_at   TEXT DEFAULT (datetime('now'))
            );
        """)

        # Seed inventory — only insert if table is empty
        existing = conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]
        if existing == 0:
            conn.executemany(
                "INSERT INTO inventory VALUES (?, ?, ?)",
                [
                    ("WidgetA",  15, 250.00),
                    ("WidgetB",  10, 500.00),
                    ("GadgetX",   5, 750.00),
                    ("FakeItem",  0,   0.00),
                ],
            )


# ── Tool functions called by the validation agent ─────────────────────────────

def query_inventory(item_name: str) -> dict:
    """Look up an item in inventory. Returns stock and unit_price, or not_found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM inventory WHERE item = ?", (item_name,)
        ).fetchone()

    if row is None:
        return {"found": False, "item": item_name}

    return {
        "found": True,
        "item": row["item"],
        "stock": row["stock"],
        "unit_price": row["unit_price"],
    }


def check_price_deviation(item_name: str, invoice_unit_price: float) -> dict:
    """
    Compare invoice unit price against the contract price in inventory.
    Flags if deviation exceeds PRICE_DEVIATION_PCT (default 10%).
    """
    record = query_inventory(item_name)
    if not record["found"]:
        return {"checked": False, "reason": f"{item_name} not in inventory"}

    contract_price = record["unit_price"]
    if contract_price == 0:
        return {"checked": True, "deviation_ok": True, "note": "contract price is zero, skipping check"}

    deviation = abs(invoice_unit_price - contract_price) / contract_price
    return {
        "checked": True,
        "item": item_name,
        "invoice_price": invoice_unit_price,
        "contract_price": contract_price,
        "deviation_pct": round(deviation * 100, 1),
        "deviation_ok": deviation <= PRICE_DEVIATION_PCT,
    }


def check_math(line_items: list[dict]) -> dict:
    """
    Verify that each line item's amount equals qty * unit_price.
    Returns a list of any mismatches found.
    """
    mismatches = []
    calculated_subtotal = 0.0

    for item in line_items:
        name = item.get("item", "?")
        qty = item.get("quantity", 0)
        price = item.get("unit_price", 0)
        stated_amount = item.get("amount")
        expected = round(qty * price, 2)
        calculated_subtotal += expected

        if stated_amount is not None:
            diff = abs(stated_amount - expected)
            if diff > 0.02:  # allow $0.02 rounding tolerance
                mismatches.append({
                    "item": name,
                    "stated": stated_amount,
                    "expected": expected,
                    "diff": round(diff, 2),
                })

    return {
        "mismatches": mismatches,
        "math_ok": len(mismatches) == 0,
        "calculated_subtotal": round(calculated_subtotal, 2),
    }


def check_duplicate(invoice_number: str) -> dict:
    """Check whether this invoice has already been processed."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT decision, processed_at FROM processed_invoices WHERE invoice_number = ?",
            (invoice_number,),
        ).fetchone()

    if row:
        return {
            "is_duplicate": True,
            "prior_decision": row["decision"],
            "processed_at": row["processed_at"],
        }
    return {"is_duplicate": False}


# ── Audit write ───────────────────────────────────────────────────────────────

def record_invoice(
    invoice_number: str,
    vendor: str,
    total: float,
    currency: str,
    decision: str,
    reasoning: str,
    transaction_id: Optional[str],
) -> None:
    """Persist the final outcome to processed_invoices for audit and duplicate detection."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO processed_invoices
              (invoice_number, vendor, total, currency, decision, reasoning, transaction_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (invoice_number, vendor, total, currency, decision, reasoning, transaction_id),
        )


def get_history() -> list[dict]:
    """Return all processed invoices ordered by most recent first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM processed_invoices ORDER BY processed_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def generate_transaction_id() -> str:
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:6].upper()
    return f"TXN-{date_str}-{suffix}"
