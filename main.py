import re
from datetime import datetime, timedelta
from fastapi import FastAPI
from typing import List, Dict, Any

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