"""Stage 6 — assemble the final mapping document. Pure code, no LLM call."""
from datetime import datetime, timezone
from typing import Optional

from pipeline.validate import TableMapping


def assemble(tables: list[TableMapping], generated_at: Optional[str] = None) -> dict:
    return {
        "mapping_version": "1.0",
        "source": "legacy_hrm (MySQL)",
        "destination": "people_platform (MongoDB)",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "tables": [t.model_dump() for t in tables],
    }
