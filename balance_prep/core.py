"""Balance preparation: from an assignment file to the balances file a collections bot reads.

Business rules:
  1. The last registered payment is subtracted from every balance. If the
     payment was larger than the balance, the result is zero, never negative:
         total_debt            = overdue_amount       - last_payment
         current_min_payment   = min_payment_current  - last_payment
         previous_min_payment  = min_payment_previous - last_payment
  2. Rows are left out when the total debt ends at zero (already paid), when
     days past due is zero or less, or when the product is not one of the valid
     products (BALANCE_PREP_VALID_PRODUCTS). Left-out products are counted by type.
  3. The product is written with a single output label (BALANCE_PREP_OUTPUT_PRODUCT).
  4. Five phones, in this order: mobile, holder, work, reference 1, reference 2.
  5. The holder name is flipped to speaking order ("GARCIA JUAN" -> "Juan Garcia");
     names that cannot be resolved stay as they came. Can be disabled.
  6. last_payment and last_payment_date are copied as they are; an empty value
     stays empty (it is not filled with zero).
  7. A current minimum payment larger than the debt is kept but counted, so it
     can be checked at the source.
"""
import datetime as dt
import os

from . import names, spreadsheet as ss

OUTPUT_COLUMNS = ["document", "name", "product", "product_number", "days_past_due", "total_debt",
                  "current_min_payment", "previous_min_payment", "last_payment", "last_payment_date",
                  "phone_1", "phone_2", "phone_3", "phone_4", "phone_5"]
WIDTHS = [13, 32, 16, 16, 13, 14, 19, 20, 13, 16, 15, 15, 15, 15, 15]
PHONES = ["phone_mobile", "phone_holder", "phone_work", "phone_ref_1", "phone_ref_2"]

ALIASES = {
    "document":            ["document_number", "document", "doc_number", "dni"],
    "holder":              ["holder", "name", "full name", "titular"],
    "product_type":        ["product_type", "product"],
    "product_number":      ["product_number", "account", "credit_number"],
    "days_past_due":       ["days_past_due", "dpd", "days overdue"],
    "overdue_amount":      ["overdue_amount", "total_debt", "amount overdue"],
    "min_payment_current": ["min_payment_current", "current minimum payment"],
    "min_payment_previous": ["min_payment_previous", "previous minimum payment"],
    "last_payment":        ["last_payment", "last payment amount"],
    "last_payment_date":   ["last_payment_date", "last payment date"],
    "phone_mobile":        ["phone_mobile", "mobile"],
    "phone_holder":        ["phone_holder", "home phone"],
    "phone_work":          ["phone_work", "work phone"],
    "phone_ref_1":         ["phone_ref_1", "reference phone 1"],
    "phone_ref_2":         ["phone_ref_2", "reference phone 2"],
}
REQUIRED = ["document", "holder", "product_type", "product_number", "days_past_due",
            "overdue_amount", "min_payment_current", "min_payment_previous"]


def settings():
    valid = os.environ.get("BALANCE_PREP_VALID_PRODUCTS") or "credit card"
    return {
        "valid_products": {ss.normalize(p) for p in valid.split(",") if p.strip()},
        "output_product": os.environ.get("BALANCE_PREP_OUTPUT_PRODUCT") or "card product",
    }


def read_base(source):
    headers, rows = ss.read_sheet(source)
    if not headers:
        raise ss.InvalidSheet("The file is empty.")
    return rows, ss.map_columns(headers, ALIASES, REQUIRED)


def discounted(amount, payment) -> float:
    """Rule 1: subtract the last payment and floor at zero. Never negative."""
    return max((amount or 0.0) - (payment or 0.0), 0.0)


def transform(base, flip_names=True, config=None, flipper=None):
    """Return (output_rows, summary)."""
    rows, pos = base
    cfg = config or settings()
    flipper = flipper or (names.NameFlipper() if flip_names else None)
    out = []
    summary = {"read": len(rows), "with_last_payment": 0, "paid_off": 0, "not_past_due": 0,
               "other_products": {}, "no_phone": 0, "min_above_debt": 0, "names_flipped": 0,
               "names_untouched": 0}
    for row in rows:
        payment = ss.number(ss.value(row, pos, "last_payment"))
        if payment is not None:
            summary["with_last_payment"] += 1
        debt = discounted(ss.number(ss.value(row, pos, "overdue_amount"), 0.0), payment)
        if debt == 0:
            summary["paid_off"] += 1
            continue
        if ss.number(ss.value(row, pos, "days_past_due"), 0.0) <= 0:
            summary["not_past_due"] += 1
            continue
        product = ss.text(ss.value(row, pos, "product_type"))
        if ss.normalize(product or "") not in cfg["valid_products"]:
            label = product or "(no product)"
            summary["other_products"][label] = summary["other_products"].get(label, 0) + 1
            continue
        current = discounted(ss.number(ss.value(row, pos, "min_payment_current"), 0.0), payment)
        previous = discounted(ss.number(ss.value(row, pos, "min_payment_previous"), 0.0), payment)
        if current > debt:
            summary["min_above_debt"] += 1
        phones = [ss.text(ss.value(row, pos, p)) for p in PHONES]
        if not any(phones):
            summary["no_phone"] += 1
        holder = ss.text(ss.value(row, pos, "holder"))
        if holder and flipper:
            holder, ok = flipper.flip(holder)
            summary["names_flipped" if ok else "names_untouched"] += 1
        out.append([ss.value(row, pos, "document"), holder, cfg["output_product"],
                    ss.value(row, pos, "product_number"), ss.value(row, pos, "days_past_due"),
                    round(debt, 2), round(current, 2), round(previous, 2), payment,
                    ss.to_date(ss.value(row, pos, "last_payment_date"))] + phones)
    summary["loaded"] = len(out)
    summary["total_debt"] = round(sum(r[5] for r in out), 2)
    summary["total_min_payment"] = round(sum(r[6] for r in out), 2)
    return out, summary


def output_name(today=None) -> str:
    return f"balances {(today or dt.date.today()).isoformat()}.xlsx"


def build_workbook(out_rows):
    wb, ws = ss.new_workbook("balances", OUTPUT_COLUMNS, WIDTHS)
    for r in out_rows:
        ws.append(r)
    for n in range(2, ws.max_row + 1):
        for col in (6, 7, 8, 9):
            ws.cell(row=n, column=col).number_format = "#,##0.00"
        ws.cell(row=n, column=10).number_format = "dd/mm/yyyy"
    ws.freeze_panes = "A2"
    return wb
