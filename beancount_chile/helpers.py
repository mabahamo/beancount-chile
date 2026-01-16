"""Helper functions for beancount-chile importers."""

from decimal import Decimal
from typing import Optional


def format_amount(amount: Optional[Decimal], currency: str = "CLP") -> str:
    """Format an amount for display."""
    if amount is None:
        return f"0.00 {currency}"
    return f"{amount:.2f} {currency}"


def normalize_payee(description: str) -> str:
    """
    Extract and normalize payee from transaction description.

    Args:
        description: Transaction description

    Returns:
        Normalized payee name
    """
    # Remove common prefixes
    description = description.strip()

    # Handle "Traspaso A:" or "Transferencia A:" patterns
    if description.startswith("Traspaso A:"):
        return description.replace("Traspaso A:", "").strip()
    if description.startswith("Transferencia A:"):
        return description.replace("Transferencia A:", "").strip()

    # Remove "Compra " prefix
    if description.startswith("Compra "):
        return description.replace("Compra ", "").strip()

    # Remove "Pago " prefix
    if description.startswith("Pago "):
        return description.replace("Pago ", "").strip()

    return description


def clean_narration(description: str) -> str:
    """
    Clean and format narration text.

    Args:
        description: Original description

    Returns:
        Cleaned narration
    """
    return " ".join(description.split())
