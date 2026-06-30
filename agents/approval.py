"""
Approval agent — applies business rules then uses the LLM to reason to a final decision.

Rules:
  - total < $10K  → standard approval prompt
  - total >= $10K → heightened scrutiny prompt (LLM instructed to be more conservative)

The LLM receives: invoice details, validation warnings, and the applicable rule context.
It returns a structured ApprovalDecision (approved | rejected + reasoning).
"""

from langchain_core.messages import HumanMessage, SystemMessage

import config
from models.invoice import ApprovalDecision, Invoice, InvoiceState

STANDARD_SYSTEM = """You are Acme Corp's accounts payable approval agent.
Review the invoice and any validation warnings, then decide: approved or rejected.
Approve if the invoice is legitimate and reasonable. Reject if something is clearly wrong.
Provide a concise business justification."""

SCRUTINY_SYSTEM = """You are Acme Corp's VP-level accounts payable approval agent.
This invoice exceeds $10,000 and requires heightened scrutiny.
Be conservative: approve only if you are confident the invoice is fully legitimate.
Flag any concerns prominently in your reasoning even if you ultimately approve.
Provide a detailed business justification."""


def approval_node(state: InvoiceState) -> dict:
    invoice = Invoice.model_validate(state["invoice"])
    warnings = state.get("warnings", [])
    total = invoice.total or 0.0

    system_prompt = (
        SCRUTINY_SYSTEM if total >= config.HIGH_VALUE_THRESHOLD else STANDARD_SYSTEM
    )

    warnings_text = (
        "\n".join(f"  - {w}" for w in warnings) if warnings else "  None"
    )

    line_items_text = "\n".join(
        f"  {item.item}: qty={item.quantity}, unit_price=${item.unit_price:.2f}"
        for item in invoice.line_items
    )

    user_message = f"""Invoice: {invoice.invoice_number}
Vendor: {invoice.vendor}
Date: {invoice.date} | Due: {invoice.due_date}
Currency: {invoice.currency}
Payment Terms: {invoice.payment_terms}

Line Items:
{line_items_text}

Total: ${total:,.2f}

Validation Warnings:
{warnings_text}

Make your approval decision."""

    llm = config.get_llm(temperature=0)
    structured_llm = llm.with_structured_output(ApprovalDecision)

    result: ApprovalDecision = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ])

    return {
        "decision": result.decision,
        "reasoning": result.reasoning,
    }


def route_after_approval(state: InvoiceState) -> str:
    return "pay" if state.get("decision") == "approved" else "reject"
