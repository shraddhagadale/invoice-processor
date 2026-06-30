"""
Acme Corp Invoice Processor
Usage:
  python main.py --invoice data/invoices/invoice_1001.txt
  python main.py --history
"""

import argparse
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from tools.inventory_db import setup_database, get_history
from workflow.graph import app


def print_separator(char="─", width=60):
    print(char * width)


def run_invoice(invoice_path: str):
    if not Path(invoice_path).exists():
        print(f"Error: file not found — {invoice_path}")
        sys.exit(1)

    print_separator("═")
    print(f"  ACME CORP — Invoice Processor")
    print_separator("═")
    print(f"  File: {invoice_path}")
    print_separator()

    initial_state = {"invoice_path": invoice_path}

    try:
        final_state = app.invoke(initial_state)
    except Exception as e:
        print(f"\n  ERROR during processing: {e}")
        sys.exit(1)

    _print_result(final_state)


def _print_result(state: dict):
    invoice = state.get("invoice") or {}
    issues   = state.get("issues", [])
    warnings = state.get("warnings", [])
    decision = state.get("final_status", "unknown").upper()
    reasoning = state.get("reasoning", "")
    txn_id   = state.get("transaction_id")

    print(f"  Invoice:  {invoice.get('invoice_number', 'N/A')}")
    print(f"  Vendor:   {invoice.get('vendor', 'N/A')}")
    print(f"  Total:    {invoice.get('currency', 'USD')} {(invoice.get('total') or 0):,.2f}")
    print(f"  Confidence: {invoice.get('confidence', 1.0):.0%}")
    print_separator()

    if issues:
        print("  VALIDATION ISSUES (critical):")
        for issue in issues:
            print(f"    ✗ {issue}")

    if warnings:
        print("  VALIDATION WARNINGS:")
        for w in warnings:
            print(f"    ⚠ {w}")

    print_separator()
    print(f"  DECISION:  {decision}")
    print(f"  REASONING: {reasoning}")

    if txn_id:
        print(f"  TRANSACTION ID: {txn_id}")

    print_separator("═")


def print_history():
    rows = get_history()
    if not rows:
        print("No invoices processed yet.")
        return

    print_separator("═")
    print("  ACME CORP — Processing History")
    print_separator("═")
    print(f"  {'Invoice':<15} {'Vendor':<30} {'Total':>10}  {'Decision':<10}  {'Processed At'}")
    print_separator()
    for r in rows:
        total = f"{r['currency']} {r['total']:,.2f}" if r["total"] else "N/A"
        print(
            f"  {r['invoice_number']:<15} {(r['vendor'] or '')[:28]:<30} "
            f"{total:>10}  {(r['decision'] or '').upper():<10}  {r['processed_at']}"
        )
    print_separator("═")


def main():
    parser = argparse.ArgumentParser(
        description="Acme Corp Automated Invoice Processor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --invoice data/invoices/invoice_1001.txt
  python main.py --invoice data/invoices/invoice_1011.pdf
  python main.py --history
        """,
    )
    parser.add_argument("--invoice", help="Path to invoice file (txt, pdf, json, csv, xml)")
    parser.add_argument("--history", action="store_true", help="Show all processed invoices")
    args = parser.parse_args()

    setup_database()

    if args.history:
        print_history()
    elif args.invoice:
        run_invoice(args.invoice)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
