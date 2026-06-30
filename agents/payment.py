"""
Payment agent — processes approved invoices via mock banking API.
Rejected invoices are logged with their justification.
All outcomes are written to the processed_invoices audit table and a log file in logs/.
"""

import os
from datetime import datetime, timezone
from models.invoice import Invoice, InvoiceState
from tools.inventory_db import generate_transaction_id, record_invoice

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")


def payment_node(state: InvoiceState) -> dict:
    invoice = Invoice.model_validate(state["invoice"])
    decision = state["decision"]
    reasoning = state["reasoning"]
    warnings = state.get("warnings", [])
    total = invoice.total or 0.0

    if decision == "approved":
        transaction_id = _mock_payment(invoice.invoice_number, total, invoice.currency)
        final_status = "approved"
    else:
        transaction_id = None
        final_status = "rejected"

    record_invoice(
        invoice_number=invoice.invoice_number,
        vendor=invoice.vendor,
        total=total,
        currency=invoice.currency,
        decision=final_status,
        reasoning=reasoning,
        transaction_id=transaction_id,
    )

    _write_log(
        invoice_number=invoice.invoice_number,
        vendor=invoice.vendor,
        total=total,
        currency=invoice.currency,
        decision=final_status,
        reasoning=reasoning,
        warnings=warnings,
        transaction_id=transaction_id,
    )

    return {
        "transaction_id": transaction_id,
        "final_status": final_status,
    }


def reject_node(state: InvoiceState) -> dict:
    """Handles rejections that originate from validation (before approval runs)."""
    invoice_data = state.get("invoice") or {}
    invoice_number = invoice_data.get("invoice_number", "UNKNOWN")
    vendor = invoice_data.get("vendor", "UNKNOWN")
    total = invoice_data.get("total") or 0.0
    currency = invoice_data.get("currency", "USD")
    issues = state.get("issues", [])
    warnings = state.get("warnings", [])
    reasoning = "Rejected at validation: " + "; ".join(issues)

    record_invoice(
        invoice_number=invoice_number,
        vendor=vendor,
        total=total,
        currency=currency,
        decision="rejected",
        reasoning=reasoning,
        transaction_id=None,
    )

    _write_log(
        invoice_number=invoice_number,
        vendor=vendor,
        total=total,
        currency=currency,
        decision="rejected",
        reasoning=reasoning,
        warnings=warnings,
        transaction_id=None,
    )

    return {
        "decision": "rejected",
        "reasoning": reasoning,
        "transaction_id": None,
        "final_status": "rejected",
    }


def _mock_payment(invoice_number: str, amount: float, currency: str) -> str:
    """Simulate a banking API call. Returns a transaction ID."""
    txn_id = generate_transaction_id()
    print(f"  [mock bank] POST /payments → {txn_id} | {invoice_number} | {currency} {amount:,.2f}")
    return txn_id


def _write_log(
    invoice_number: str,
    vendor: str,
    total: float,
    currency: str,
    decision: str,
    reasoning: str,
    warnings: list,
    transaction_id: str | None,
) -> None:
    """Write a human-readable log file to logs/<invoice_number>.log"""
    os.makedirs(LOGS_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    log_path = os.path.join(LOGS_DIR, f"{invoice_number}.log")

    lines = [
        f"Timestamp:      {timestamp}",
        f"Invoice:        {invoice_number}",
        f"Vendor:         {vendor}",
        f"Total:          {currency} {total:,.2f}",
        f"Decision:       {decision.upper()}",
        f"Reasoning:      {reasoning}",
    ]

    if warnings:
        lines.append("Warnings:")
        for w in warnings:
            lines.append(f"  - {w}")

    if transaction_id:
        lines.append(f"Transaction ID: {transaction_id}")
    else:
        lines.append("Transaction ID: N/A — payment not processed")

    with open(log_path, "w") as f:
        f.write("\n".join(lines) + "\n")
