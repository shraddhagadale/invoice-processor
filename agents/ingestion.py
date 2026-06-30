"""
Ingestion agent — extracts a structured Invoice from raw file content.

Flow:
  1. For JSON/CSV/XML: deterministic parser (no LLM needed)
  2. For PDF/TXT: LLM with structured output
  3. If confidence < threshold: self-correction retry (max 2 attempts)
     — re-prompts with the prior extraction attempt in context
"""

from langchain_core.messages import HumanMessage, SystemMessage

import config
from models.invoice import Invoice, InvoiceState
from tools.parsers import parse_structured

EXTRACTION_SYSTEM_PROMPT = """You are an invoice data extraction specialist.
Extract structured invoice data from the provided text.
Be precise with numbers. If a field is missing or ambiguous, use null.
Set confidence to a value between 0 and 1 reflecting how certain you are about the extraction:
- 1.0: clean, unambiguous invoice
- 0.7–0.9: mostly clear with minor issues
- below 0.7: messy, OCR artifacts, missing fields, or suspicious data"""

CORRECTION_SYSTEM_PROMPT = """You are an invoice data extraction specialist performing a correction.
Your previous extraction attempt had low confidence. Review both the original text and your prior
attempt, identify what went wrong, and produce a corrected extraction."""


def ingestion_node(state: InvoiceState) -> dict:
    raw_content = state["raw_content"]
    file_format = state["file_format"]
    retry_count = state.get("retry_count", 0)

    # ── Deterministic path for structured formats ─────────────────────────────
    if file_format in ("json", "csv", "xml"):
        parsed = parse_structured(raw_content, file_format)
        if parsed:
            invoice = Invoice.model_validate(parsed)
            return {"invoice": invoice.model_dump(), "retry_count": retry_count}

    # ── LLM extraction for PDF/TXT (or fallback if deterministic parse failed) ─
    llm = config.get_llm(temperature=0)
    structured_llm = llm.with_structured_output(Invoice)

    if retry_count == 0:
        messages = [
            SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=f"Extract the invoice data from this text:\n\n{raw_content}"),
        ]
    else:
        prior = state.get("invoice", {})
        messages = [
            SystemMessage(content=CORRECTION_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Original invoice text:\n\n{raw_content}\n\n"
                    f"Your prior extraction (confidence was too low):\n{prior}\n\n"
                    "Please correct the extraction."
                )
            ),
        ]

    try:
        invoice: Invoice = structured_llm.invoke(messages)
    except Exception as e:
        raise RuntimeError(f"Ingestion agent failed (attempt {retry_count + 1}): {e}") from e

    return {"invoice": invoice.model_dump(), "retry_count": retry_count + 1}


def should_retry(state: InvoiceState) -> str:
    """Conditional edge: retry if confidence is low and retries remain."""
    invoice_data = state.get("invoice", {})
    confidence = invoice_data.get("confidence", 1.0)
    retry_count = state.get("retry_count", 0)

    if confidence < config.CONFIDENCE_THRESHOLD and retry_count < config.MAX_RETRY_ATTEMPTS:
        return "retry"
    return "validate"
