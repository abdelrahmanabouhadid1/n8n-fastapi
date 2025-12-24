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