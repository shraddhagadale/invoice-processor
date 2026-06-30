"""
Payment agent — processes approved invoices via mock banking API.
Rejected invoices are logged with their justification.
All outcomes are written to the processed_invoices audit table.
"""

from models.invoice import Invoice, InvoiceState
from tools.inventory_db import generate_transaction_id, record_invoice


def payment_node(state: InvoiceState) -> dict:
    invoice = Invoice.model_validate(state["invoice"])
    decision = state["decision"]
    reasoning = state["reasoning"]
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
