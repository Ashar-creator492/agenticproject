import csv
import io
from collections.abc import Iterable
from typing import Any

REPORT_COLUMNS = (
    "Section",
    "Item",
    "Product",
    "Lot",
    "Retailer",
    "Reference",
    "Quantity",
    "Status",
    "Notes",
    "Date",
)


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _safe_cell(value: Any) -> str:
    """Keep spreadsheet applications from executing packet text as a formula."""
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text


def _row(
    section: str,
    item: str,
    *,
    product: Any = "",
    lot: Any = "",
    retailer: Any = "",
    reference: Any = "",
    quantity: Any = "",
    status: Any = "",
    notes: Any = "",
    date: Any = "",
) -> dict[str, str]:
    values = (section, item, product, lot, retailer, reference, quantity, status, notes, date)
    return dict(zip(REPORT_COLUMNS, (_safe_cell(value) for value in values), strict=True))


def manufacturer_report_rows(packet: dict[str, Any]) -> Iterable[dict[str, str]]:
    product = _record(packet.get("product"))
    manufacturer = _record(product.get("manufacturer"))
    batch = _record(packet.get("batch"))
    summary = _record(packet.get("distribution_summary"))
    product_name = product.get("name") or batch.get("product_name") or ""
    lot = batch.get("batch_number") or ""

    # Flatten each packet section into rows that nontechnical reviewers can scan.
    yield _row("Case", "Case reference", reference=packet.get("case_public_id"))
    yield _row(
        "Product",
        "Product identity",
        product=product_name,
        lot=lot,
        reference=product.get("sku"),
        notes=f"Manufacturer: {manufacturer.get('name', '')}",
    )
    yield _row(
        "Batch",
        "Stock summary",
        product=product_name,
        lot=lot,
        quantity=batch.get("quantity_received"),
        notes=(
            f"Shipped: {summary.get('quantity_shipped', batch.get('quantity_shipped', ''))}; "
            f"retained by importer: "
            f"{summary.get('quantity_retained', batch.get('quantity_retained', ''))}"
        ),
        date=batch.get("expiry_date"),
    )

    for shipment in _records(packet.get("distribution")):
        yield _row(
            "Distribution",
            "Shipment recipient",
            product=product_name,
            lot=lot,
            retailer=shipment.get("retailer_name") or shipment.get("retailer_code"),
            reference=shipment.get("shipment_reference"),
            quantity=shipment.get("quantity"),
            status="Shipped",
            date=shipment.get("shipped_at"),
        )

    for finding in _records(packet.get("findings")):
        yield _row(
            "Retailer finding",
            "Human stock inspection",
            product=product_name,
            lot=lot,
            retailer=finding.get("retailer_name") or finding.get("retailer_code"),
            reference=finding.get("inspection_id"),
            status=str(finding.get("finding", "")).replace("_", " ").title(),
            notes=finding.get("notes"),
            date=finding.get("completed_at"),
        )

    for evidence in _records(packet.get("evidence")):
        yield _row(
            "Evidence",
            "Attached file",
            product=product_name,
            lot=lot,
            reference=evidence.get("filename"),
            status=evidence.get("content_type"),
            notes="Evidence is available in the Escalera manufacturer portal.",
            date=evidence.get("created_at"),
        )

    questions = packet.get("requested_actions") or packet.get("manufacturer_questions") or []
    if isinstance(questions, list):
        for index, question in enumerate(questions, start=1):
            yield _row(
                "Requested action",
                f"Manufacturer request {index}",
                product=product_name,
                lot=lot,
                notes=question,
            )

    if packet.get("importer_notes"):
        yield _row(
            "Importer review",
            "Approved handoff notes",
            product=product_name,
            lot=lot,
            notes=packet["importer_notes"],
        )


def manufacturer_report_csv(packet: dict[str, Any]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=REPORT_COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(manufacturer_report_rows(packet))
    return output.getvalue()
