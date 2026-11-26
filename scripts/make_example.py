"""Generate examples/assignment.csv: 20 synthetic rows (fixed seed).

Names are random combinations of the public given-name list and common
surnames; documents and phones use fictional ranges; amounts are random.
A few rows are built on purpose to exercise every rule (paid off, not past
due, another product, empty last payment).
"""
import csv
import datetime as dt
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SURNAMES = ["GOMEZ", "PEREZ", "RODRIGUEZ", "FERNANDEZ", "LOPEZ", "MARTINEZ", "SANCHEZ", "ROMERO",
            "TORRES", "RUIZ", "DIAZ", "ALVAREZ", "DE LA FUENTE", "DEL VALLE"]


def main(seed=11, rows=20):
    rnd = random.Random(seed)
    first = [l.split("#", 1)[0].strip() for l in (ROOT / "data" / "first_names.txt").read_text(encoding="utf-8").splitlines()]
    first = [f for f in first if f]
    (ROOT / "examples").mkdir(exist_ok=True)
    with open(ROOT / "examples" / "assignment.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["document_number", "holder", "product_type", "product_number", "days_past_due",
                    "overdue_amount", "min_payment_current", "min_payment_previous", "last_payment",
                    "last_payment_date", "phone_mobile", "phone_holder", "phone_work", "phone_ref_1", "phone_ref_2"])
        for i in range(1, rows + 1):
            overdue = rnd.randint(40, 900) * 100
            minimum = rnd.randint(5, 30) * 100
            payment = rnd.choice([None, 0, rnd.randint(1, 30) * 100])
            product, dpd = "Credit card", rnd.randint(1, 180)
            if i == 3:
                payment = overdue + 5000          # paid more than owed -> zero, left out
            if i == 7:
                dpd = 0                           # not past due -> left out
            if i == 12:
                product = "Personal loan"         # other product -> left out
            phones = [f"999{rnd.randint(0, 9999999):07d}" if rnd.random() < 0.7 else "" for _ in range(5)]
            w.writerow([f"9{i:07d}", f"{rnd.choice(SURNAMES)} {rnd.choice(first)} {rnd.choice(first)}", product,
                        f"PRD{i:05d}", dpd, overdue, minimum, minimum + rnd.randint(0, 9) * 100,
                        "" if payment is None else payment,
                        "" if payment is None else (dt.date(2026, 1, 5) + dt.timedelta(days=rnd.randint(0, 20))).isoformat()]
                       + phones)


if __name__ == "__main__":
    main()
