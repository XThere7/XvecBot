"""
services/field_schema.py
Shared field-definition and submission validation for agent actions.

Lead Capture, Data Collection and Custom Forms all let a business owner define
the structured information an agent should collect. Keeping the validation in
one place means a field behaves identically everywhere (dashboard form builder,
conversation directive, public form submission and CSV export).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Iterable

MAX_FIELDS = 50
DEFAULT_MAX_LENGTH = 500
MAX_TEXT_LENGTH = 10_000

# Canonical types used by the backend. Aliases from the UI ("text",
# "textarea", "dropdown", "checkbox") are normalised to these.
FIELD_TYPES = {
    "short_text",
    "long_text",
    "email",
    "phone",
    "number",
    "select",
    "boolean",
    "date",
}

_TYPE_ALIASES = {
    "text": "short_text",
    "string": "short_text",
    "input": "short_text",
    "textarea": "long_text",
    "longtext": "long_text",
    "dropdown": "select",
    "option": "select",
    "checkbox": "boolean",
    "yes_no": "boolean",
    "yesno": "boolean",
}

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,49}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9\s().-]{5,24}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalise_field_type(raw: Any) -> str:
    value = str(raw or "").strip().lower().replace(" ", "_")
    value = _TYPE_ALIASES.get(value, value)
    return value if value in FIELD_TYPES else "short_text"


def _coerce_options(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [part for part in raw.split(",")]
    if not isinstance(raw, Iterable):
        return []
    options: list[str] = []
    for item in raw:
        text = str(item).strip()
        if text and text not in options:
            options.append(text[:200])
    return options[:50]


def normalise_fields(fields: Any) -> list[dict[str, Any]]:
    """
    Validate and normalise an owner-defined field list.

    Raises ValueError with a user-facing message when the definition is
    unusable (duplicate keys, invalid key, select with no options, ...).
    """
    if fields is None:
        return []
    if not isinstance(fields, list):
        raise ValueError("Fields must be a list.")
    if len(fields) > MAX_FIELDS:
        raise ValueError(f"An action can have at most {MAX_FIELDS} fields.")

    normalised: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(fields):
        if not isinstance(raw, dict):
            raise ValueError(f"Field {index + 1} is not a valid field definition.")
        key = str(raw.get("key") or "").strip().lower().replace(" ", "_")
        if not _KEY_RE.match(key):
            raise ValueError(
                "Field keys must start with a letter and contain only lowercase "
                "letters, numbers and underscores."
            )
        if key in seen:
            raise ValueError(f"Duplicate field key: {key}.")
        seen.add(key)

        label = str(raw.get("label") or key.replace("_", " ").title()).strip()[:120]
        field_type = normalise_field_type(raw.get("type"))
        required = bool(raw.get("required", False))
        options = _coerce_options(raw.get("options"))
        if field_type == "select" and not options:
            raise ValueError(f"Dropdown field '{label}' needs at least one option.")

        max_length = raw.get("max_length")
        if max_length is not None:
            try:
                max_length = max(1, min(MAX_TEXT_LENGTH, int(max_length)))
            except (TypeError, ValueError):
                max_length = DEFAULT_MAX_LENGTH
        elif field_type == "long_text":
            max_length = MAX_TEXT_LENGTH
        else:
            max_length = DEFAULT_MAX_LENGTH

        entry: dict[str, Any] = {
            "key": key,
            "label": label,
            "type": field_type,
            "required": required,
            "max_length": max_length,
        }
        if options:
            entry["options"] = options
        placeholder = str(raw.get("placeholder") or "").strip()
        if placeholder:
            entry["placeholder"] = placeholder[:200]
        help_text = str(raw.get("help_text") or "").strip()
        if help_text:
            entry["help_text"] = help_text[:300]
        normalised.append(entry)
    return normalised


def _coerce_value(field: dict[str, Any], raw: Any) -> tuple[Any, str | None]:
    """Return (cleaned_value, error). Empty values are handled by the caller."""
    field_type = field["type"]
    label = field["label"]
    if raw is None:
        return None, None

    if field_type in ("short_text", "long_text", "select"):
        text = str(raw).strip()
        if not text:
            return "", None
        max_length = int(field.get("max_length") or DEFAULT_MAX_LENGTH)
        if len(text) > max_length:
            return None, f"{label} must be at most {max_length} characters."
        if field_type == "select":
            options = field.get("options") or []
            if options and text not in options:
                return None, f"{label} must be one of: {', '.join(options)}."
        return text, None

    if field_type == "email":
        text = str(raw).strip()
        if not text:
            return "", None
        if len(text) > 254 or not _EMAIL_RE.match(text):
            return None, f"Enter a valid email address for {label}."
        return text.lower(), None

    if field_type == "phone":
        text = str(raw).strip()
        if not text:
            return "", None
        digits = re.sub(r"\D", "", text)
        if not _PHONE_RE.match(text) or not (7 <= len(digits) <= 15):
            return None, f"Enter a valid phone number for {label}."
        return text, None

    if field_type == "number":
        if isinstance(raw, bool):
            return None, f"{label} must be a number."
        try:
            number = float(str(raw).strip())
        except (TypeError, ValueError):
            return None, f"{label} must be a number."
        return int(number) if number.is_integer() else number, None

    if field_type == "boolean":
        if isinstance(raw, bool):
            return raw, None
        text = str(raw).strip().lower()
        if text in ("true", "yes", "y", "1", "on", "checked"):
            return True, None
        if text in ("false", "no", "n", "0", "off", "unchecked"):
            return False, None
        return None, f"{label} must be yes or no."

    if field_type == "date":
        text = str(raw).strip()
        if not text:
            return "", None
        if not _DATE_RE.match(text):
            return None, f"{label} must use the YYYY-MM-DD date format."
        try:
            date.fromisoformat(text)
        except ValueError:
            return None, f"{label} is not a valid date."
        return text, None

    return str(raw).strip(), None


def validate_submission(
    fields: list[dict[str, Any]],
    data: Any,
    *,
    allow_partial: bool = False,
    require_consent: bool = False,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """
    Validate submitted values against a field definition.

    Returns ``(cleaned, missing_required, errors)``. Unknown keys are ignored so
    a visitor cannot inject arbitrary columns into a stored JSON document.
    """
    if not isinstance(data, dict):
        data = {}
    cleaned: dict[str, Any] = {}
    missing: list[str] = []
    errors: list[str] = []

    if require_consent:
        consent = data.get("_consent", data.get("consent"))
        if consent is not True and str(consent).strip().lower() not in (
            "true",
            "yes",
            "1",
            "on",
        ):
            errors.append("Consent is required before this information can be saved.")

    for field in fields:
        key = field["key"]
        if key not in data:
            if field.get("required"):
                missing.append(field["label"])
            continue
        value, error = _coerce_value(field, data.get(key))
        if error:
            errors.append(error)
            continue
        if value is None or value == "":
            if field.get("required"):
                missing.append(field["label"])
            continue
        cleaned[key] = value

    if missing and not allow_partial:
        errors.append("Missing required information: " + ", ".join(missing) + ".")
    return cleaned, missing, errors


def data_to_csv_rows(
    fields: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> tuple[list[str], list[list[Any]]]:
    """Turn stored JSON submissions into a header row + data rows for CSV."""
    keys = [field["key"] for field in fields]
    labels = [field["label"] for field in fields]
    output: list[list[Any]] = []
    for row in rows:
        output.append([row.get(key, "") for key in keys])
    return labels, output
