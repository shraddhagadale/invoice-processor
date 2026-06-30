"""
Validation agent — runs deterministic checks against the inventory DB.

Checks (in order):
  1. Duplicate invoice number
  2. Each line item exists in inventory
  3. Requested quantity does not exceed stock
  4. Unit price within 10% of contract price
  5. Line item math is correct

Produces:
  issues   — critical blockers that will cause rejection
  warnings — non-blocking flags passed to approval agent
"""

from models.invoice import Invoice, InvoiceState
from tools.inventory_db import (
    check_duplicate,
    query_inventory,
    check_price_deviation,
    check_math,
)


def validation_node(state: InvoiceState) -> dict:
    invoice = Invoice.model_validate(state["invoice"])
    issues: list[str] = []
    warnings: list[str] = []

    # 1. Duplicate check
    dup = check_duplicate(invoice.invoice_number)
    if dup["is_duplicate"]:
        issues.append(
            f"Duplicate invoice: {invoice.invoice_number} was already processed on "
            f"{dup['processed_at']} with decision '{dup['prior_decision']}'."
        )
        return {"issues": issues, "warnings": warnings}

    # 2 & 3. Inventory existence + stock check
    for item in invoice.line_items:
        if item.quantity <= 0:
            issues.append(
                f"'{item.item}': invalid quantity {item.quantity} — must be greater than zero."
            )
            continue

        record = query_inventory(item.item)

        if not record["found"]:
            issues.append(f"Unknown item '{item.item}' — not found in inventory.")
            continue

        if record["stock"] == 0:
            issues.append(f"'{item.item}' has zero stock — cannot fulfil order.")
            continue

        if item.quantity > record["stock"]:
            issues.append(
                f"'{item.item}': requested {item.quantity} units but only "
                f"{record['stock']} in stock."
            )

    # 4. Price deviation check
    for item in invoice.line_items:
        result = check_price_deviation(item.item, item.unit_price)
        if not result.get("checked"):
            continue
        if result.get("deviation_ok") is False:
            direction = "above" if item.unit_price > result["contract_price"] else "below"
            warnings.append(
                f"'{item.item}': invoice price ${item.unit_price:.2f} is "
                f"{result['deviation_pct']}% {direction} contract price "
                f"${result['contract_price']:.2f}."
            )

    # 5. Math check
    line_items_dicts = [i.model_dump() for i in invoice.line_items]
    math_result = check_math(line_items_dicts)
    if not math_result["math_ok"]:
        for mismatch in math_result["mismatches"]:
            issues.append(
                f"Math error on '{mismatch['item']}': stated ${mismatch['stated']:.2f} "
                f"but expected ${mismatch['expected']:.2f} "
                f"(diff ${mismatch['diff']:.2f})."
            )

    # Non-USD currency — flag as warning
    if invoice.currency and invoice.currency.upper() != "USD":
        warnings.append(
            f"Invoice is in {invoice.currency}, not USD. "
            "Amounts require conversion before payment."
        )

    return {"issues": issues, "warnings": warnings}


def has_critical_issues(state: InvoiceState) -> str:
    """Conditional edge: if any critical issues exist, reject immediately."""
    return "reject" if state.get("issues") else "approve"
