"""
Multi-format invoice parsers.
Deterministic parsing for JSON, CSV, XML.
Raw text extraction for PDF and TXT (fed to LLM in ingestion agent).
"""

import json
import csv
import io
import xml.etree.ElementTree as ET
from pathlib import Path


def detect_format(invoice_path: str) -> str:
    suffix = Path(invoice_path).suffix.lower().lstrip(".")
    if suffix in ("txt", "pdf", "json", "csv", "xml"):
        return suffix
    raise ValueError(f"Unsupported file format: {suffix}")


def load_raw(invoice_path: str) -> tuple[str, str]:
    """
    Read the invoice file and return (raw_content, file_format).
    For structured formats, raw_content is the file text.
    For PDF, raw_content is extracted text via pdfplumber.
    """
    fmt = detect_format(invoice_path)

    if fmt == "pdf":
        return _extract_pdf(invoice_path), "pdf"

    with open(invoice_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    return content, fmt


def _extract_pdf(path: str) -> str:
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pdfplumber is required for PDF parsing: pip install pdfplumber")

    text_parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)

    return "\n".join(text_parts)


def parse_structured(raw_content: str, file_format: str) -> dict | None:
    """
    Attempt deterministic parsing for JSON, CSV, XML.
    Returns a normalized dict if successful, None if format needs LLM.
    """
    try:
        if file_format == "json":
            return _parse_json(raw_content)
        if file_format == "csv":
            return _parse_csv(raw_content)
        if file_format == "xml":
            return _parse_xml(raw_content)
    except Exception:
        pass  # fall through to LLM extraction
    return None


def _parse_json(content: str) -> dict:
    data = json.loads(content)

    vendor = data.get("vendor", {})
    vendor_name = vendor.get("name", vendor) if isinstance(vendor, dict) else str(vendor)

    line_items = []
    for item in data.get("line_items", []):
        line_items.append({
            "item": item.get("item", ""),
            "quantity": float(item.get("quantity", 0)),
            "unit_price": float(item.get("unit_price", 0)),
            "amount": float(item["amount"]) if "amount" in item else None,
            "note": item.get("note"),
        })

    return {
        "invoice_number": str(data.get("invoice_number", "")),
        "vendor": vendor_name,
        "date": data.get("date"),
        "due_date": data.get("due_date"),
        "line_items": line_items,
        "subtotal": data.get("subtotal"),
        "tax_amount": data.get("tax_amount"),
        "total": data.get("total"),
        "currency": data.get("currency", "USD"),
        "payment_terms": data.get("payment_terms"),
        "confidence": 1.0,
    }


def _parse_csv(content: str) -> dict:
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        raise ValueError("Empty CSV")

    header = [h.strip().lower() for h in rows[0]]

    # Detect format: key-value CSV (invoice_1006) vs tabular (invoice_1007/1015)
    if header[0] == "field" and header[1] == "value":
        return _parse_kv_csv(rows[1:])
    else:
        return _parse_tabular_csv(header, rows[1:])


def _parse_kv_csv(rows: list) -> dict:
    kv = {}
    line_items = []
    i = 0
    while i < len(rows):
        if len(rows[i]) < 2:
            i += 1
            continue
        key, val = rows[i][0].strip(), rows[i][1].strip()
        if key == "item":
            item = {"item": val, "quantity": 0, "unit_price": 0.0}
            if i + 1 < len(rows) and rows[i + 1][0].strip() == "quantity":
                item["quantity"] = float(rows[i + 1][1].strip())
                i += 1
            if i + 1 < len(rows) and rows[i + 1][0].strip() == "unit_price":
                item["unit_price"] = float(rows[i + 1][1].strip())
                i += 1
            line_items.append(item)
        else:
            kv[key] = val
        i += 1

    return {
        "invoice_number": kv.get("invoice_number", ""),
        "vendor": kv.get("vendor", ""),
        "date": kv.get("date"),
        "due_date": kv.get("due_date"),
        "line_items": line_items,
        "subtotal": float(kv["subtotal"]) if "subtotal" in kv else None,
        "tax_amount": float(kv["tax"]) if "tax" in kv else None,
        "total": float(kv["total"]) if "total" in kv else None,
        "currency": "USD",
        "payment_terms": kv.get("payment_terms"),
        "confidence": 1.0,
    }


def _parse_tabular_csv(header: list, rows: list) -> dict:
    meta = {}
    line_items = []

    for row in rows:
        if not any(c.strip() for c in row):
            continue
        d = dict(zip(header, [c.strip() for c in row]))

        # Rows with item data
        item_name = d.get("item") or d.get("")
        qty_raw = d.get("qty", "")
        price_raw = d.get("unit price", "")
        total_raw = d.get("line total", "")

        if item_name and qty_raw and price_raw:
            try:
                line_items.append({
                    "item": item_name,
                    "quantity": float(qty_raw),
                    "unit_price": float(price_raw),
                    "amount": float(total_raw) if total_raw else None,
                })
            except ValueError:
                pass

        # Capture invoice-level meta from first data row
        if not meta and d.get("invoice number"):
            meta = {
                "invoice_number": d.get("invoice number", ""),
                "vendor": d.get("vendor", ""),
                "date": d.get("date"),
                "due_date": d.get("due date"),
            }

    return {
        **meta,
        "line_items": line_items,
        "currency": "USD",
        "confidence": 1.0,
    }


def _parse_xml(content: str) -> dict:
    root = ET.fromstring(content)

    def text(tag: str) -> str | None:
        el = root.find(f".//{tag}")
        return el.text.strip() if el is not None and el.text else None

    line_items = []
    for item_el in root.findall(".//item"):
        name = item_el.findtext("name", "").strip()
        qty = float(item_el.findtext("quantity", "0"))
        price = float(item_el.findtext("unit_price", "0"))
        line_items.append({
            "item": name,
            "quantity": qty,
            "unit_price": price,
            "amount": round(qty * price, 2),
        })

    subtotal = text("subtotal")
    tax_amount = text("tax_amount")
    total = text("total")

    return {
        "invoice_number": text("invoice_number") or "",
        "vendor": text("vendor") or "",
        "date": text("date"),
        "due_date": text("due_date"),
        "line_items": line_items,
        "subtotal": float(subtotal) if subtotal else None,
        "tax_amount": float(tax_amount) if tax_amount else None,
        "total": float(total) if total else None,
        "currency": text("currency") or "USD",
        "payment_terms": text("payment_terms"),
        "confidence": 1.0,
    }
