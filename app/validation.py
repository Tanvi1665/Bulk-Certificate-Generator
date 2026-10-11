"""Validation rules for ONE recipient row.

Why separate from the request schema? A bad row must not reject the whole
request, so rows are validated one by one and bad ones are recorded as failed.
"""
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError, field_validator


def ensure_supported_text(value: str) -> str:
    """The built-in PDF fonts support Latin-1 only (A-Z, accents like é/ñ...).
    Reject anything else up front instead of printing broken glyphs."""
    if not value.isprintable():
        raise ValueError("must not contain control characters or line breaks")
    try:
        value.encode("latin-1")
    except UnicodeEncodeError:
        raise ValueError("contains characters not supported by the certificate font (Latin-1 only)")
    return value


class RecipientData(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr

    @field_validator("name")
    @classmethod
    def _name_supported(cls, v: str) -> str:
        return ensure_supported_text(v)


def validate_recipient(raw: Any) -> tuple[RecipientData | None, str | None]:
    """Return (clean_recipient, None) on success or (None, error_message)."""
    if not isinstance(raw, dict):
        return None, "Recipient must be an object with 'name' and 'email'"
    try:
        return RecipientData.model_validate(raw), None
    except ValidationError as exc:
        problems = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
        return None, "; ".join(problems)
