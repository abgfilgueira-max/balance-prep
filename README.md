# balance-prep

Command-line utility that turns a collections assignment file into the balances file a collections
bot reads, with each customer's last payment already discounted.

> This is a cleaned-up extract of an internal platform that runs in production. Client, vendor and
> employee names, credentials, hosts and all real data were removed. `examples/assignment.csv` is
> synthetic.

## Run it

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
cp .env.example .env                             # optional; or export the variables
python scripts/make_example.py                   # regenerates the synthetic example
python -m balance_prep examples/assignment.csv --out output
pytest
```

Input can be `.xlsx` or `.csv`. Column headers are matched ignoring case, accents and punctuation;
each field accepts several names (see `ALIASES` in `balance_prep/core.py`).

| Variable | Default | Meaning |
|---|---|---|
| `BALANCE_PREP_VALID_PRODUCTS` | `credit card` | comma-separated products that are loaded |
| `BALANCE_PREP_OUTPUT_PRODUCT` | `card product` | label written in the output `product` column |
| `BALANCE_PREP_OUTPUT_DIR` | current folder | where the output file is written |
| `BALANCE_PREP_FIRST_NAMES_FILE` | `data/first_names.txt` | given-name list used to flip names |

## Business rules

1. The last payment is subtracted from the overdue amount and from both minimum payments.
   A payment larger than the balance leaves it at **zero, never negative**.
2. Rows are left out when the debt ends at zero, when days past due is zero or less, or when the
   product is not a valid product; left-out products are counted by type.
3. One output product label for every row.
4. Five phones in fixed order: mobile, holder, work, reference 1, reference 2.
5. The holder name is flipped to speaking order (`GARCIA JUAN` → `Juan Garcia`); unresolved names stay
   as they came. `--raw-names` disables it.
6. An empty last payment stays empty; it is not filled with zero.
7. A current minimum larger than the debt is kept but counted, so the source can be checked.
