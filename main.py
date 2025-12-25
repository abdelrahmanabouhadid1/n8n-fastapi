import re
import math

from datetime import datetime, timedelta
from fastapi import FastAPI , HTTPException
from typing import List, Dict, Any , Optional, Tuple
from __future__ import annotations

from pydantic import BaseModel, Field

app = FastAPI(title="n8n FastAPI Service", version="1.0.0")


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/build")
def build():
    return {"build": "force-4-decimals-v1"}


@app.post("/format-project-code")
def format_project_code(items: List[Dict[str, Any]]):
    output = []

    for item in items:
        row = dict(item)  # keep all fields

        value = row.get("Project Code")

        # keep empty as empty
        if value is None or value == "":
            output.append(row)
            continue

        try:
            # force ANY numeric value to 4 decimals
            f = float(value)
            row["Project Code"] = f"{f:.4f}"
        except Exception:
            # keep non-numeric as is
            row["Project Code"] = value

        output.append(row)

    return output

@app.post("/clean-keys")
def clean_keys(items: List[Dict[str, Any]]):
    cleaned_items: List[Dict[str, Any]] = []

    for item in items:
        cleaned: Dict[str, Any] = {}

        for key, value in item.items():
            # 1) Clean key (remove newlines + trim spaces)
            new_key = str(key).replace("\n", "").strip()

            # 2) Skip empty Excel columns (__EMPTY, __EMPTY_1, ...)
            if new_key.startswith("__EMPTY"):
                continue

            # 3) Skip keys that became empty after cleaning
            if new_key == "":
                continue

            cleaned[new_key] = value

        cleaned_items.append(cleaned)

    return cleaned_items

@app.post("/split-project-field")
def split_project_field(items: List[Dict[str, Any]]):
    results: List[Dict[str, Any]] = []

    for item in items:
        data = dict(item)  # copy original json

        value = data.get("Project")
        if isinstance(value, str):
            # Match: number (with optional dots) - rest of text
            match = re.match(r'^([0-9.]+)\s*-\s*(.*)$', value.strip())
            if match:
                project_code = match.group(1).strip()
                project_name = match.group(2).strip()

                # Remove original Project field
                data.pop("Project", None)

                # Add new fields
                data["Project Code"] = project_code
                data["Project"] = project_name

        results.append(data)

    return results

@app.post("/merge-old-new")
def merge_old_new(items: List[Dict[str, Any]]):
    # -----------------------------------
    # 1) Classify rows into OLD vs NEW
    # -----------------------------------
    old_projects = {}   # key = Project Code
    new_by_code = {}    # key = Project Code

    for item in items:
        data = dict(item)

        # Skip rows without Project Code
        if "Project Code" not in data:
            continue

        code = str(data.get("Project Code", "")).strip()

        # OLD rows contain "#"
        if "#" in data:
            old_projects[code] = data
        else:
            # NEW dataset rows
            new_by_code[code] = data

    # -----------------------------------
    # 2) Compute add / remove / common
    # -----------------------------------
    old_codes = set(old_projects.keys())
    new_codes = set(new_by_code.keys())

    common_codes = old_codes & new_codes
    add_codes    = new_codes - old_codes
    remove_codes = old_codes - new_codes

    # -----------------------------------
    # 3) Build final merged list
    # -----------------------------------
    final = []

    # 3.a Merge & keep old rows
    for code, old_data in old_projects.items():

        # Skip removed ones
        if code in remove_codes:
            continue

        # Common → merge old + new (new overwrites)
        if code in common_codes:
            merged = dict(old_data)
            merged.update(new_by_code[code])
            final.append(merged)

        else:
            # Not removed + not common → keep old as-is
            final.append(old_data)

    # 3.b Add new-only rows
    for code in add_codes:
        new_row = new_by_code.get(code)
        if new_row:
            final.append(dict(new_row))

    return final

def excel_serial_to_date_str(value):
    """
    Convert an Excel serial date to 'DD/MM/YYYY'.
    If value is empty/invalid, return empty string or original value.
    """
    if value in (None, "", 0):
        return ""

    try:
        # Work with strings, ints, or floats
        s = str(value).strip()
        if not s:
            return ""

        n = int(float(s))

        # Fix cases like 452890 -> 45289 (extra trailing zero)
        if n > 60000:
            n = n // 10

        # Excel base date workaround (1900 leap year bug)
        base_date = datetime(1899, 12, 30)
        d = base_date + timedelta(days=n)

        return d.strftime("%d/%m/%Y")

    except Exception:
        # If conversion fails, return original value
        return value


@app.post("/convert-excel-dates")
def convert_excel_dates(items: List[Dict[str, Any]]):
    output_items: List[Dict[str, Any]] = []

    for item in items:
        row = dict(item)  # copy to avoid mutating original

        for col in ["Opening-planned", "Date of Latest Update"]:
            if col in row and row[col] not in (None, ""):
                row[col] = excel_serial_to_date_str(row[col])

        # Preserve order exactly
        output_items.append(row)

    return output_items




# =========================================================
# Models
# =========================================================

class InsightsRequest(BaseModel):
    """
    rows: list of JSON objects (each object = one row from Excel/DB export)
    config: optional overrides for column names and thresholds
    """
    rows: List[Dict[str, Any]] = Field(..., min_items=1)
    config: Optional[Dict[str, Any]] = None


# =========================================================
# Defaults (adjust if your headers differ)
# =========================================================

DEFAULT_COLS = {
    "total_cost": "TOTAL COST",
    "sela_fees": "SELA FEES",
    "wht": "WHT",
    "vat_amount": "VAT AMOUNT",
    "total_budget": "TOTAL BUDGET",
    "actual_pr": "ACTUAL PR",
    "actual_po": "ACTUAL PO",
    "vat_pct": "VAT %",
    "sela_pct": "SELA FEES %",
    "line_desc": "BUDGET LINE ITEM DESCRIPTION",
    "line_no": "BUDGET LINE ITEM #",
    "category": "CATEGORY",
    "vendor": "VENDOR",
    "project": "PROJECT NAME",   # sometimes PROJECT_NAME
    "bu": "BU",
}

DEFAULT_THRESHOLDS = {
    "top_n": 10,
    "vat_expected_min": 1000.0,   # ignore tiny expectations
    "vat_diff_abs_min": 5000.0,   # flag if abs diff > this
    "vat_diff_pct_min": 0.05,     # or diff > 5% of expected
    "max_label_len": 80,
}

_percent_re = re.compile(r"^\s*(-?\d+(\.\d+)?)\s*%\s*$")


# =========================================================
# Helpers
# =========================================================

def to_number(x: Any) -> float:
    """Parse messy numeric cells: commas, '-', blanks, percent strings -> float."""
    if x is None:
        return 0.0
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        try:
            if isinstance(x, float) and math.isnan(x):
                return 0.0
        except Exception:
            pass
        return float(x)

    s = str(x).strip()
    if s in ("", "-", "—", "–", "N/A", "NA", "nan", "None"):
        return 0.0

    m = _percent_re.match(s)
    if m:
        try:
            return float(m.group(1)) / 100.0
        except Exception:
            return 0.0

    s = s.replace(" ", "").replace(",", "")
    s = re.sub(r"[–—]", "-", s)

    try:
        return float(s)
    except Exception:
        return 0.0


def safe_div(a: float, b: float) -> float:
    return a / b if b not in (0, 0.0, None) else 0.0


def short_label(x: Any, max_len: int) -> str:
    s = "" if x is None else str(x).strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def get_cols_and_thresholds(config: Optional[Dict[str, Any]]) -> Tuple[Dict[str, str], Dict[str, Any]]:
    cols = DEFAULT_COLS.copy()
    thr = DEFAULT_THRESHOLDS.copy()

    if config:
        cols.update((config.get("columns", {}) or {}))
        thr.update((config.get("thresholds", {}) or {}))
    return cols, thr


def require_keys_in_dataset(rows: List[Dict[str, Any]], required_keys: List[str]) -> None:
    present = set()
    for r in rows:
        present.update(r.keys())
    missing = [k for k in required_keys if k not in present]
    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Missing required columns in input rows",
                "missing": missing,
                "hint": "Fix your headers OR pass config.columns overrides.",
                "present_sample": sorted(list(present))[:60],
            },
        )


def group_sum(rows: List[Dict[str, Any]], group_key: str, value_key: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for r in rows:
        k = str(r.get(group_key, "")).strip()
        v = to_number(r.get(value_key))
        out[k] = out.get(k, 0.0) + v
    return out


# =========================================================
# Core Insights Logic
# =========================================================

def compute_insights(rows: List[Dict[str, Any]], cols: Dict[str, str], thr: Dict[str, Any]) -> Dict[str, Any]:
    required = [
        cols["total_cost"], cols["sela_fees"], cols["vat_amount"],
        cols["total_budget"], cols["actual_pr"], cols["actual_po"],
    ]
    require_keys_in_dataset(rows, required)

    # Resolve project column if needed
    project_key = cols["project"]
    dataset_keys = set().union(*(r.keys() for r in rows))
    if project_key not in dataset_keys and "PROJECT_NAME" in dataset_keys:
        project_key = "PROJECT_NAME"

    # Choose line label column
    line_label_key = cols["line_desc"] if cols["line_desc"] in dataset_keys else cols["line_no"]

    base_cost = sum(to_number(r.get(cols["total_cost"])) for r in rows)
    sela_fees = sum(to_number(r.get(cols["sela_fees"])) for r in rows)
    wht = sum(to_number(r.get(cols["wht"])) for r in rows) if cols["wht"] in dataset_keys else 0.0
    vat = sum(to_number(r.get(cols["vat_amount"])) for r in rows)
    total_budget = sum(to_number(r.get(cols["total_budget"])) for r in rows)

    actual_pr = sum(to_number(r.get(cols["actual_pr"])) for r in rows)
    actual_po = sum(to_number(r.get(cols["actual_po"])) for r in rows)

    remaining_pr = max(total_budget - actual_pr, 0.0)
    remaining_po = max(total_budget - actual_po, 0.0)

    add_ons = max(total_budget - base_cost, 0.0)
    uplift_pct = safe_div(add_ons, base_cost)

    # Top drivers by total budget
    top_n = int(thr["top_n"])
    by_line_budget = group_sum(rows, line_label_key, cols["total_budget"])
    top_drivers = sorted(by_line_budget.items(), key=lambda kv: kv[1], reverse=True)[:top_n]

    # Top remaining PR exposure by line item
    remaining_by_line: Dict[str, float] = {}
    for r in rows:
        label = str(r.get(line_label_key, "")).strip()
        tb = to_number(r.get(cols["total_budget"]))
        pr = to_number(r.get(cols["actual_pr"]))
        remaining_by_line[label] = remaining_by_line.get(label, 0.0) + max(tb - pr, 0.0)
    top_remaining_pr = sorted(remaining_by_line.items(), key=lambda kv: kv[1], reverse=True)[:top_n]

    # VAT basis flags: expected VAT = VAT% * (TOTAL_COST + SELA_FEES)
    vat_flags: List[Dict[str, Any]] = []
    vat_pct_key = cols["vat_pct"]
    if vat_pct_key in dataset_keys:
        for r in rows:
            vat_pct = to_number(r.get(vat_pct_key))
            if vat_pct <= 0:
                continue

            base = to_number(r.get(cols["total_cost"]))
            fees = to_number(r.get(cols["sela_fees"]))
            expected = vat_pct * (base + fees)
            if expected < float(thr["vat_expected_min"]):
                continue

            actual = to_number(r.get(cols["vat_amount"]))
            diff = actual - expected
            diff_pct = safe_div(diff, expected)

            if (abs(diff) >= float(thr["vat_diff_abs_min"])) or (abs(diff_pct) >= float(thr["vat_diff_pct_min"])):
                vat_flags.append({
                    "line_item": short_label(r.get(line_label_key), int(thr["max_label_len"])),
                    "vat_pct": vat_pct,
                    "expected_vat": expected,
                    "actual_vat": actual,
                    "diff": diff,
                    "diff_pct": diff_pct,
                })

        vat_flags.sort(key=lambda x: abs(x["diff"]), reverse=True)
        vat_flags = vat_flags[:15]

    # Data quality counters
    def count_zero(key: str) -> int:
        return sum(1 for r in rows if to_number(r.get(key)) == 0.0)

    def count_missing(key: str) -> int:
        return sum(1 for r in rows if r.get(key) in (None, "", "-", "—", "–"))

    dq = {
        "rows_total": len(rows),
        "zero_total_budget_rows": count_zero(cols["total_budget"]),
        "zero_actual_pr_rows": count_zero(cols["actual_pr"]),
        "zero_actual_po_rows": count_zero(cols["actual_po"]),
        "missing_line_item_label_rows": count_missing(line_label_key),
        "missing_vat_pct_rows": count_missing(vat_pct_key) if vat_pct_key in dataset_keys else None,
    }

    # Optional breakdowns for AI charting
    breakdowns: Dict[str, Any] = {}

    if cols["category"] in dataset_keys:
        by_cat = group_sum(rows, cols["category"], cols["total_budget"])
        breakdowns["by_category_total_budget"] = sorted(
            [{"category": k, "value": v} for k, v in by_cat.items() if k],
            key=lambda x: x["value"],
            reverse=True
        )[:25]

    if cols["vendor"] in dataset_keys:
        by_vendor = group_sum(rows, cols["vendor"], cols["total_budget"])
        breakdowns["by_vendor_total_budget"] = sorted(
            [{"vendor": k, "value": v} for k, v in by_vendor.items() if k],
            key=lambda x: x["value"],
            reverse=True
        )[:25]

    if project_key in dataset_keys:
        by_project = group_sum(rows, project_key, cols["total_budget"])
        breakdowns["by_project_total_budget"] = sorted(
            [{"project": k, "value": v} for k, v in by_project.items() if k],
            key=lambda x: x["value"],
            reverse=True
        )[:25]

    # AI-ready bullets + chart suggestions
    bullets = [
        f"Total budget = {total_budget:,.2f} SAR; base cost = {base_cost:,.2f} SAR.",
        f"Add-ons (fees/taxes/etc.) = {add_ons:,.2f} SAR (~{uplift_pct*100:.1f}% uplift over base).",
        f"Actual PR = {actual_pr:,.2f} SAR; remaining PR exposure = {remaining_pr:,.2f} SAR.",
        f"Actual PO = {actual_po:,.2f} SAR; remaining PO exposure = {remaining_po:,.2f} SAR.",
        f"VAT basis flags detected = {len(vat_flags)} (rule: VAT ≈ VAT% × (base+SELA fees)).",
    ]

    chart_suggestions = [
        {
            "chart": "waterfall",
            "title": "Cost build-up (Base → Fees → WHT → VAT → Total Budget)",
            "series": [
                {"name": "Base Cost", "value": base_cost},
                {"name": "SELA Fees", "value": sela_fees},
                {"name": "WHT", "value": wht},
                {"name": "VAT", "value": vat},
                {"name": "Total Budget", "value": total_budget},
            ],
        },
        {
            "chart": "donut",
            "title": "Base vs Add-ons Share",
            "series": [
                {"name": "Base Cost", "value": base_cost},
                {"name": "Add-ons", "value": add_ons},
            ],
        },
        {
            "chart": "bar_horizontal",
            "title": f"Top {top_n} Cost Drivers (by Total Budget)",
            "series": [{"name": k, "value": v} for k, v in top_drivers],
        },
        {
            "chart": "bar",
            "title": "Budget vs PR vs Remaining",
            "series": [
                {"name": "Total Budget", "value": total_budget},
                {"name": "Actual PR", "value": actual_pr},
                {"name": "Remaining PR", "value": remaining_pr},
            ],
        },
    ]

    return {
        "meta": {
            "input_rows": len(rows),
            "line_item_label_used": line_label_key,
            "columns_used": {
                **cols,
                "project_resolved": cols["project"],
                "project_used": project_key,
            },
            "thresholds": thr,
        },
        "kpis": {
            "base_cost": base_cost,
            "sela_fees": sela_fees,
            "wht": wht,
            "vat": vat,
            "total_budget": total_budget,
            "actual_pr": actual_pr,
            "remaining_pr": remaining_pr,
            "actual_po": actual_po,
            "remaining_po": remaining_po,
            "add_ons": add_ons,
            "uplift_pct": uplift_pct,
        },
        "top": {
            "top_drivers_total_budget": [{"label": k, "value": v} for k, v in top_drivers],
            "top_remaining_pr": [{"label": k, "value": v} for k, v in top_remaining_pr],
        },
        "breakdowns": breakdowns,
        "flags": {
            "vat_basis_flags": vat_flags,
            "data_quality": dq,
        },
        "bullets": bullets,
        "chart_suggestions": chart_suggestions,
    }


# =========================================================
# Endpoints (attach to your existing app)
# =========================================================

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/insights")
def insights(req: InsightsRequest):
    cols, thr = get_cols_and_thresholds(req.config)
    try:
        return compute_insights(req.rows, cols, thr)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "Failed to compute insights", "message": str(e)})