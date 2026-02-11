"""Tests for helper functions."""

import unicodedata
from datetime import date

from beancount_chile.helpers import generate_receipt_link


class TestGenerateReceiptLink:
    """Tests for generate_receipt_link."""

    def test_empty_paths_returns_empty_frozenset(self):
        result = generate_receipt_link(date(2024, 1, 15), "Test", [])
        assert result == frozenset()

    def test_returns_frozenset_with_single_link(self):
        result = generate_receipt_link(date(2024, 1, 15), "Test", ["/receipts/a.pdf"])
        assert len(result) == 1
        (link,) = result
        assert link.startswith("rcpt-")
        assert len(link) == 13  # "rcpt-" + 8 hex chars

    def test_deterministic_same_inputs(self):
        args = (date(2024, 3, 10), "Amazon", ["/receipts/invoice.pdf"])
        assert generate_receipt_link(*args) == generate_receipt_link(*args)

    def test_nfc_and_nfd_produce_same_hash(self):
        """macOS uses NFD paths, Linux uses NFC; the hash must be identical."""
        nfc_path = unicodedata.normalize("NFC", "/recibos/factura-año.pdf")
        nfd_path = unicodedata.normalize("NFD", "/recibos/factura-año.pdf")
        # Confirm the two strings are actually different byte sequences
        assert nfc_path != nfd_path

        d = date(2024, 6, 1)
        payee = "Proveedor"
        assert generate_receipt_link(d, payee, [nfc_path]) == generate_receipt_link(
            d, payee, [nfd_path]
        )

    def test_nfc_nfd_multiple_paths(self):
        """Mixed NFC/NFD across multiple paths still produces the same hash."""
        nfc = unicodedata.normalize("NFC", "ñ")
        nfd = unicodedata.normalize("NFD", "ñ")

        paths_nfc = [f"/a/{nfc}.pdf", f"/b/{nfc}.pdf"]
        paths_nfd = [f"/a/{nfd}.pdf", f"/b/{nfd}.pdf"]

        d = date(2024, 6, 1)
        assert generate_receipt_link(d, "P", paths_nfc) == generate_receipt_link(
            d, "P", paths_nfd
        )

    def test_path_order_does_not_matter(self):
        d = date(2024, 1, 1)
        paths_a = ["/receipts/a.pdf", "/receipts/b.pdf"]
        paths_b = ["/receipts/b.pdf", "/receipts/a.pdf"]
        assert generate_receipt_link(d, "X", paths_a) == generate_receipt_link(
            d, "X", paths_b
        )

    def test_different_inputs_produce_different_hashes(self):
        d = date(2024, 1, 1)
        link_a = generate_receipt_link(d, "A", ["/a.pdf"])
        link_b = generate_receipt_link(d, "B", ["/a.pdf"])
        link_c = generate_receipt_link(d, "A", ["/b.pdf"])
        link_d = generate_receipt_link(date(2024, 1, 2), "A", ["/a.pdf"])
        assert len({frozenset(s) for s in [link_a, link_b, link_c, link_d]}) == 4
