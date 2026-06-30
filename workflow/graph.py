"""LangGraph StateGraph — wires all agents and routing logic together."""

from langgraph.graph import StateGraph, END

from models.invoice import InvoiceState
from agents.ingestion import ingestion_node, should_retry
from agents.validation import validation_node, has_critical_issues
from agents.approval import approval_node, route_after_approval
from agents.payment import payment_node, reject_node
from tools.parsers import load_raw


def load_raw_node(state: InvoiceState) -> dict:
    raw_content, file_format = load_raw(state["invoice_path"])
    return {
        "raw_content": raw_content,
        "file_format": file_format,
        "retry_count": 0,
        "issues": [],
        "warnings": [],
        "decision": "",
        "reasoning": "",
        "transaction_id": None,
        "final_status": "",
    }


def build_graph():
    graph = StateGraph(InvoiceState)

    graph.add_node("load_raw",  load_raw_node)
    graph.add_node("extract",   ingestion_node)
    graph.add_node("validate",  validation_node)
    graph.add_node("approve",   approval_node)
    graph.add_node("pay",       payment_node)
    graph.add_node("reject",    reject_node)

    graph.set_entry_point("load_raw")
    graph.add_edge("load_raw", "extract")

    # Self-correction loop in ingestion
    graph.add_conditional_edges(
        "extract",
        should_retry,
        {"retry": "extract", "validate": "validate"},
    )

    # Validation → approve or immediate reject
    graph.add_conditional_edges(
        "validate",
        has_critical_issues,
        {"approve": "approve", "reject": "reject"},
    )

    # Approval → pay or reject
    graph.add_conditional_edges(
        "approve",
        route_after_approval,
        {"pay": "pay", "reject": "reject"},
    )

    graph.add_edge("pay",    END)
    graph.add_edge("reject", END)

    return graph.compile()


app = build_graph()
