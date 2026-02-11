"""Helper functions for beancount-chile importers."""

import hashlib
import unicodedata
from datetime import date as date_type
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from beancount.core import data


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


def generate_receipt_link(
    date: date_type, payee: str, receipt_paths: List[str]
) -> frozenset:
    """Return a frozenset with a deterministic receipt link, or empty frozenset.

    The link ID is a SHA-256 hash of the date, payee, and sorted NFC-normalized
    receipt paths, ensuring stable hashes across macOS (NFD) and Linux (NFC).
    """
    if not receipt_paths:
        return frozenset()
    date_str = date.isoformat()
    normalized_paths = [unicodedata.normalize("NFC", p) for p in receipt_paths]
    paths_str = ",".join(sorted(normalized_paths))
    hash_input = f"{date_str}:{payee}:{paths_str}"
    link_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
    return frozenset([f"rcpt-{link_hash}"])


def create_receipt_documents(
    receipt_paths: List[str],
    filepath: Path,
    date: date_type,
    account_name: str,
    links: frozenset,
) -> List[data.Document]:
    """Return a list of data.Document entries for the given receipt paths."""
    documents: List[data.Document] = []
    for receipt_path in receipt_paths:
        doc = data.Document(
            meta=data.new_metadata(str(filepath), 0),
            date=date,
            account=account_name,
            filename=receipt_path,
            tags=frozenset(),
            links=links if links else frozenset(),
        )
        documents.append(doc)
    return documents


def clean_narration(description: str) -> str:
    """
    Clean and format narration text.

    Args:
        description: Original description

    Returns:
        Cleaned narration
    """
    return " ".join(description.split())
