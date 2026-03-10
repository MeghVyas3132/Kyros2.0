from io import BytesIO
from pathlib import Path

import pandas as pd


def dataframe_from_bytes(content: bytes) -> pd.DataFrame:
    return pd.read_csv(BytesIO(content))


def dataframes_from_upload(content: bytes, filename: str) -> dict[str, pd.DataFrame]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        return {"Sheet1": pd.read_csv(BytesIO(content))}

    if suffix in {".xlsx", ".xlsm"}:
        return pd.read_excel(BytesIO(content), sheet_name=None)

    raise ValueError(f"Unsupported file format: {suffix}")


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")
