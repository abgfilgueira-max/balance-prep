"""Small helpers to read .xlsx/.csv files and write .xlsx output.

Columns are matched ignoring case, accents and punctuation, and every field
accepts several header names, so a renamed column in the source export does
not break the tools.
"""
import csv
import datetime as dt
import io
import re
import unicodedata
from pathlib import Path

from openpyxl import Workbook, load_workbook

EXCEL_EPOCH = dt.date(1899, 12, 30)


class InvalidSheet(ValueError):
    """The file opened, but it does not contain what we expected."""

    def __init__(self, message, detail=""):
        super().__init__(message if not detail else f"{message}\n{detail}")
        self.message = message
        self.detail = detail


def normalize(name) -> str:
    """Make a header comparable: no accents, no case, no punctuation."""
    plain = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", plain.lower())


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _is_excel(source) -> bool:
    """An .xlsx file is a zip archive: it starts with PK. Anything else is read as CSV."""
    if hasattr(source, "read"):
        source.seek(0)
        sig = source.read(2)
        source.seek(0)
        return sig == b"PK"
    with open(source, "rb") as f:
        return f.read(2) == b"PK"


def _decode(source) -> str:
    raw = source.read() if hasattr(source, "read") else Path(source).read_bytes()
    if hasattr(source, "seek"):
        source.seek(0)
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _csv_value(raw: str):
    """CSV cells are text. Numbers become numbers, except codes with a leading zero."""
    s = raw.strip()
    if not s:
        return None
    if s.startswith("0") and s != "0" and not s.startswith("0."):
        return s
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return s


def _read_csv(source):
    text = _decode(source)
    if not text.strip():
        return [], []
    sample = text[:8000]
    try:
        sep = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        first = sample.splitlines()[0] if sample.splitlines() else ""
        sep = max(",;\t|", key=first.count) if first else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=sep))
    if not rows:
        return [], []
    headers = [c.strip() for c in rows[0]]
    while headers and not headers[-1]:
        headers.pop()
    width = len(headers)
    data = []
    for row in rows[1:]:
        if not any(c.strip() for c in row):
            continue
        values = [_csv_value(c) for c in row[:width]]
        data.append(values + [None] * (width - len(values)))
    return headers, data


def read_sheet(source, sheet=None):
    """Return (headers, rows). `source` is a path or a file object, .xlsx or .csv."""
    if not _is_excel(source):
        return _read_csv(source)
    wb = load_workbook(source, read_only=True, data_only=True)
    try:
        ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb[wb.sheetnames[0]]
        it = ws.iter_rows(values_only=True)
        try:
            headers = list(next(it))
        except StopIteration:
            return [], []
        while headers and headers[-1] is None:
            headers.pop()
        width = len(headers)
        data = []
        for row in it:
            if all(c is None for c in row):
                continue
            data.append(list(row[:width]) + [None] * (width - len(row)))
        return headers, data
    finally:
        wb.close()


def map_columns(headers, aliases, required):
    """Locate every field among the headers. Return {field: index}."""
    present = {}
    for i, name in enumerate(headers):
        if name is not None:
            present.setdefault(normalize(name), i)
    positions, missing = {}, []
    for field, names in aliases.items():
        idx = next((present[normalize(n)] for n in names if normalize(n) in present), None)
        if idx is not None:
            positions[field] = idx
        elif field in required:
            missing.append(names[0])
    if missing:
        raise InvalidSheet("Missing columns: " + ", ".join(missing),
                           "Found: " + ", ".join(str(h) for h in headers if h))
    return positions


def value(row, positions, field):
    i = positions.get(field)
    return None if i is None else row[i]


def number(raw, default=None):
    if raw is None or raw == "":
        return default
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    try:
        return float(str(raw).strip().replace(",", "."))
    except ValueError:
        return default


def text(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def to_date(raw):
    """Accept a date, an Excel serial number or text (ISO or dd/mm/yyyy)."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, dt.datetime):
        return raw
    if isinstance(raw, dt.date):
        return dt.datetime.combine(raw, dt.time.min)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        serial = int(raw)
        if serial <= 0:
            return None
        return dt.datetime.combine(EXCEL_EPOCH + dt.timedelta(days=serial), dt.time.min)
    s = str(raw).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"^(\d{2})[/.](\d{2})[/.](\d{4})", s)
    if m:
        return dt.datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def day_of(raw):
    d = to_date(raw)
    return d.date() if d else None


def new_workbook(sheet_title, headers, widths=None):
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for i, w in enumerate(widths or [], start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    return wb, ws


def to_bytes(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
