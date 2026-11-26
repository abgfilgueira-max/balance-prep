"""Business rules of the balance preparation, on synthetic data only."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from balance_prep import cli, core, spreadsheet  # noqa: E402

EXAMPLE = ROOT / "examples" / "assignment.csv"
HEADERS = ["document_number", "holder", "product_type", "product_number", "days_past_due", "overdue_amount",
           "min_payment_current", "min_payment_previous", "last_payment", "last_payment_date",
           "phone_mobile", "phone_holder", "phone_work", "phone_ref_1", "phone_ref_2"]
CFG = {"valid_products": {spreadsheet.normalize("credit card")}, "output_product": "card product"}


def run(rows, **kw):
    pos = spreadsheet.map_columns(HEADERS, core.ALIASES, core.REQUIRED)
    return core.transform((rows, pos), config=CFG, **kw)


def row(overdue=5000, m1=800, m2=900, payment=None, dpd=30, product="Credit card", phones=("9990000001",)):
    phones = list(phones) + [None] * (5 - len(phones))
    return ["90000001", "GARCIA JUAN", product, "PRD1", dpd, overdue, m1, m2, payment, None] + phones


@pytest.mark.parametrize("amount, payment", [(5000, 0), (5000, 4999), (5000, 5000), (5000, 7000), (0, 300), (None, None)])
def test_discounted_is_never_negative(amount, payment):
    assert core.discounted(amount, payment) >= 0


def test_balance_never_negative_on_the_synthetic_file():
    out, summary = core.transform(core.read_base(EXAMPLE), config=CFG)
    assert out, "the example should leave rows to load"
    for r in out:
        assert r[5] > 0                       # total debt: zero rows are left out
        assert r[6] >= 0 and r[7] >= 0        # minimum payments floored at zero


def test_payment_larger_than_debt_leaves_the_row_out():
    out, summary = run([row(overdue=5000, payment=6000)])
    assert out == [] and summary["paid_off"] == 1


def test_minimums_are_discounted_and_floored():
    out, _ = run([row(overdue=5000, m1=800, m2=900, payment=850)])
    assert out[0][5] == 4150 and out[0][6] == 0 and out[0][7] == 50


def test_not_past_due_and_other_products_are_left_out():
    out, summary = run([row(dpd=0), row(product="Personal loan"), row()])
    assert len(out) == 1
    assert summary["not_past_due"] == 1
    assert summary["other_products"] == {"Personal loan": 1}


def test_empty_last_payment_stays_empty():
    out, summary = run([row(payment=None)])
    assert out[0][8] is None and summary["with_last_payment"] == 0


def test_phone_order_and_name_flip():
    out, _ = run([row(phones=("9990000001", "9990000002", "", "9990000004", "9990000005"))])
    assert out[0][10:15] == ["9990000001", "9990000002", None, "9990000004", "9990000005"]
    assert out[0][1] == "Juan Garcia"
    out, _ = run([row()], flip_names=False)
    assert out[0][1] == "GARCIA JUAN"


def test_min_above_debt_is_counted_not_dropped():
    out, summary = run([row(overdue=500, m1=800)])
    assert len(out) == 1 and summary["min_above_debt"] == 1


def test_cli_writes_the_output(tmp_path, monkeypatch):
    monkeypatch.setenv("BALANCE_PREP_VALID_PRODUCTS", "credit card")
    assert cli.main([str(EXAMPLE), "--out", str(tmp_path)]) == 0
    assert list(tmp_path.glob("balances *.xlsx"))
