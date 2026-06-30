from __future__ import annotations

from typing import Optional, List, Literal
from typing_extensions import TypedDict
from pydantic import BaseModel, Field


class LineItem(BaseModel):
    item: str = Field(description="Product or item name")
    quantity: float = Field(description="Quantity ordered")
    unit_price: float = Field(description="Price per unit in invoice currency")
    amount: Optional[float] = Field(default=None, description="Line total (qty * unit_price)")
    note: Optional[str] = Field(default=None, description="Any notes on this line item")

    def calculated_amount(self) -> float:
        return round(self.quantity * self.unit_price, 2)


class Invoice(BaseModel):
    invoice_number: str = Field(description="Unique invoice identifier, e.g. INV-1001")
    vendor: str = Field(description="Vendor or supplier name")
    date: Optional[str] = Field(default=None, description="Invoice date as YYYY-MM-DD")
    due_date: Optional[str] = Field(default=None, description="Payment due date as YYYY-MM-DD")
    line_items: List[LineItem] = Field(description="All line items on this invoice")
    subtotal: Optional[float] = Field(default=None, description="Sum of line items before tax")
    tax_amount: Optional[float] = Field(default=None, description="Tax charged")
    total: Optional[float] = Field(default=None, description="Grand total including tax")
    currency: str = Field(default="USD", description="Currency code, e.g. USD or EUR")
    payment_terms: Optional[str] = Field(default=None, description="e.g. Net 30")
    confidence: float = Field(
        default=1.0,
        description="Extraction confidence 0–1. Low for messy/ambiguous input.",
    )
    notes: Optional[str] = Field(default=None, description="Any additional notes or flags")


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"] = Field(
        description="Final approval decision"
    )
    reasoning: str = Field(
        description="Clear business justification for the decision"
    )


# LangGraph state — flows through every node
class InvoiceState(TypedDict):
    # Input
    invoice_path: str

    # After load_raw
    raw_content: str
    file_format: str  # pdf | txt | json | csv | xml

    # After extract
    invoice: Optional[dict]   # serialized Invoice (use Invoice.model_validate)
    retry_count: int

    # After validate
    issues: List[str]         # critical blockers — trigger rejection
    warnings: List[str]       # non-blocking flags — passed to approval

    # After approve
    decision: str             # "approved" | "rejected"
    reasoning: str

    # After payment
    transaction_id: Optional[str]
    final_status: str         # "approved" | "rejected" | "failed"
