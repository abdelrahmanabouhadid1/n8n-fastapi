from fastapi import FastAPI
from typing import List, Dict, Any

app = FastAPI()

@app.post("/format-project-code")
def format_project_code(items: List[Dict[str, Any]]):
    output = []

    for item in items:
        row = dict(item)

        value = row.get("Project Code")

        if value is not None and value != "":
            try:
                f = float(value)
                # Always force 4 decimals (even for integers)
                row["Project Code"] = f"{f:.4f}"
            except Exception:
                row["Project Code"] = value

        output.append(row)

    return output