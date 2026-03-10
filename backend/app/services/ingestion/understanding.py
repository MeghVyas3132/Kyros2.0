from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any

from app.services.ingestion.mapping import (
    UPLOAD_FIELD_ALIASES,
    UPLOAD_REQUIRED_FIELDS,
    normalize_column_name,
)


DATA_UNDERSTANDING_MIN_CONFIDENCE = 0.86


@dataclass
class FieldMatch:
    semantic_field: str
    source_column: str | None
    confidence: float
    match_type: str


@dataclass
class SheetDetection:
    sheet_name: str
    sheet_type: str
    upload_type: str | None
    confidence: float


def _norm(value: str) -> str:
    return normalize_column_name(value)


def _sheet_tokens(sheet_name: str) -> set[str]:
    cleaned = _norm(sheet_name).replace("-", " ").replace("/", " ")
    return {part for part in cleaned.split() if part}


SHEET_TYPE_TO_UPLOAD_TYPE: dict[str, str | None] = {
    "STORE_GRADES": "STORE_GRADES",
    "BUY_FILE": "BUY_FILE",
    "SALES_HISTORY": "SALES",
    "SIZE_GUIDE": "SIZE_GUIDE",
    "GRN": "GRN",
    "UNKNOWN": None,
}


SHEET_FINGERPRINTS: dict[str, dict[str, list[str]]] = {
    "STORE_GRADES": {
        "must": ["store name", "product", "grade"],
        "should": ["price band", "region", "store grade - prod price band"],
        "name_hints": ["store", "grade"],
    },
    "BUY_FILE": {
        "must": ["style number", "store group", "size"],
        "should": [
            "style group",
            "total buy qty",
            "ecom reserved qty",
            "reserved qty for ars",
            "story",
        ],
        "name_hints": ["buy", "ss", "plan"],
    },
    "SALES_HISTORY": {
        "must": ["store name", "style_number", "sales qty"],
        "should": ["size_final", "department", "net sales", "region", "priceband"],
        "name_hints": ["sales", "history"],
    },
    "SIZE_GUIDE": {
        "must": ["size", "min / max", "size type"],
        "should": ["product", "store name"],
        "name_hints": ["size", "guide"],
    },
    "GRN": {
        "must": ["grn code", "grn date", "units received"],
        "should": ["sku code", "style number", "warehouse", "supplier"],
        "name_hints": ["grn", "receipt"],
    },
}


def _best_similarity(column_name: str, candidates: list[str]) -> float:
    column_norm = _norm(column_name)
    best = 0.0
    for candidate in candidates:
        ratio = difflib.SequenceMatcher(a=column_norm, b=_norm(candidate)).ratio()
        if ratio > best:
            best = ratio
    return best


def detect_sheet_type(sheet_name: str, df_columns: list[str]) -> SheetDetection:
    normalized_columns = [_norm(column) for column in df_columns]
    sheet_name_tokens = _sheet_tokens(sheet_name)

    best_type = "UNKNOWN"
    best_score = 0.0
    second_score = 0.0

    for sheet_type, fingerprint in SHEET_FINGERPRINTS.items():
        must = fingerprint["must"]
        should = fingerprint["should"]

        must_hits = 0
        for token in must:
            if any(_best_similarity(column, [token]) >= 0.9 for column in normalized_columns):
                must_hits += 1

        if must_hits == 0:
            score = 0.0
        else:
            should_hits = 0
            for token in should:
                if any(_best_similarity(column, [token]) >= 0.88 for column in normalized_columns):
                    should_hits += 1

            name_hint_hits = 0
            for hint in fingerprint["name_hints"]:
                if hint in sheet_name_tokens:
                    name_hint_hits += 1

            must_score = (must_hits / max(len(must), 1)) * 0.7
            should_score = (should_hits / max(len(should), 1)) * 0.2
            name_score = (name_hint_hits / max(len(fingerprint["name_hints"]), 1)) * 0.1
            score = must_score + should_score + name_score

        if score > best_score:
            second_score = best_score
            best_score = score
            best_type = sheet_type
        elif score > second_score:
            second_score = score

    if best_score < 0.40:
        best_type = "UNKNOWN"

    confidence = max(0.0, min(1.0, best_score - (second_score * 0.2)))
    upload_type = SHEET_TYPE_TO_UPLOAD_TYPE.get(best_type)

    return SheetDetection(
        sheet_name=sheet_name,
        sheet_type=best_type,
        upload_type=upload_type,
        confidence=round(confidence, 3),
    )


def suggest_mapping_with_confidence(
    upload_type: str,
    df_columns: list[str],
    stored_mapping: dict[str, str] | None = None,
    manual_mapping: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, float], list[str], list[str]]:
    aliases = UPLOAD_FIELD_ALIASES.get(upload_type, {})
    required = UPLOAD_REQUIRED_FIELDS.get(upload_type, [])

    available_columns = list(df_columns)
    available_lookup = {_norm(column): column for column in available_columns}
    used_columns: set[str] = set()

    mapping: dict[str, str] = {}
    confidence: dict[str, float] = {}

    if stored_mapping:
        for field, source in stored_mapping.items():
            if field in aliases and source in available_columns:
                mapping[field] = source
                confidence[field] = 1.0
                used_columns.add(source)

    if manual_mapping:
        for field, source in manual_mapping.items():
            if field in aliases and source in available_columns:
                mapping[field] = source
                confidence[field] = 1.0
                used_columns.add(source)

    for field, candidates in aliases.items():
        if field in mapping:
            continue

        best_column: str | None = None
        best_score = 0.0
        best_match_type = "none"

        normalized_candidates = [_norm(candidate) for candidate in candidates]

        for candidate in normalized_candidates:
            if candidate in available_lookup:
                candidate_column = available_lookup[candidate]
                if candidate_column not in used_columns:
                    best_column = candidate_column
                    best_score = 1.0
                    best_match_type = "exact"
                    break

        if best_column is None:
            for column in available_columns:
                if column in used_columns:
                    continue
                score = _best_similarity(column, candidates)
                if score > best_score:
                    best_score = score
                    best_column = column
                    best_match_type = "fuzzy"

        if best_column is None:
            continue

        threshold = 0.82 if field in required else 0.88
        if best_score >= threshold:
            mapping[field] = best_column
            confidence[field] = round(best_score, 3)
            used_columns.add(best_column)
            if best_match_type == "exact":
                confidence[field] = 1.0

    missing_required = [field for field in required if field not in mapping]
    low_conf_required = [
        field for field in required if field in mapping and confidence.get(field, 0.0) < DATA_UNDERSTANDING_MIN_CONFIDENCE
    ]

    return mapping, confidence, missing_required, low_conf_required


def mapping_confidence_score(
    required_fields: list[str],
    confidence_by_field: dict[str, float],
) -> float:
    if not required_fields:
        return 1.0
    values = [confidence_by_field.get(field, 0.0) for field in required_fields]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)


def sheet_understanding_payload(
    *,
    detection: SheetDetection,
    upload_type: str | None,
    columns: list[str],
    mapping: dict[str, str],
    confidence: dict[str, float],
    missing_required: list[str],
    low_conf_required: list[str],
) -> dict[str, Any]:
    mapping_required = bool(missing_required or low_conf_required)
    return {
        "sheet_name": detection.sheet_name,
        "detected_sheet_type": detection.sheet_type,
        "detected_upload_type": upload_type,
        "classifier_confidence": detection.confidence,
        "mapping_confidence": mapping_confidence_score(
            UPLOAD_REQUIRED_FIELDS.get(upload_type or "", []),
            confidence,
        ) if upload_type else 0.0,
        "available_columns": columns,
        "suggested_mapping": mapping,
        "field_confidence": confidence,
        "missing_fields": missing_required,
        "low_confidence_required_fields": low_conf_required,
        "requires_confirmation": mapping_required,
    }
