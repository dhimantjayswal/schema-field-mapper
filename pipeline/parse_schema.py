"""Stage 0 — normalize the two hand-transcribed schema literals into
canonical field records with description strings ready for embedding.
"""
from dataclasses import dataclass
from typing import Optional

from data.dest_schema import DEST_SCHEMA
from data.source_schema import SOURCE_SCHEMA


@dataclass(frozen=True)
class SourceField:
    table: str
    field: str
    type: str
    pk: bool = False
    fk: Optional[str] = None
    unique: bool = False
    nullable: bool = True
    comment: Optional[str] = None

    @property
    def description(self) -> str:
        bits = [f"{self.table}.{self.field}", self.type]
        if self.pk:
            bits.append("PRIMARY KEY")
        if self.fk:
            bits.append(f"FK -> {self.fk}")
        if self.comment:
            bits.append(self.comment)
        return " — ".join(bits)


@dataclass(frozen=True)
class DestField:
    collection: str
    path: str
    type: str
    ref: Optional[str] = None
    comment: Optional[str] = None

    @property
    def description(self) -> str:
        bits = [f"{self.collection}.{self.path}", self.type]
        if self.ref:
            bits.append(f"ref -> {self.ref}")
        if self.comment:
            bits.append(self.comment)
        return " — ".join(bits)


def load_source_fields() -> list[SourceField]:
    fields = []
    for table, cols in SOURCE_SCHEMA["tables"].items():
        for col in cols:
            fields.append(SourceField(
                table=table,
                field=col["field"],
                type=col["type"],
                pk=col.get("pk", False),
                fk=col.get("fk"),
                unique=col.get("unique", False),
                nullable=col.get("nullable", True),
                comment=col.get("comment"),
            ))
    return fields


def load_dest_fields() -> list[DestField]:
    fields = []
    for collection, cols in DEST_SCHEMA["collections"].items():
        for col in cols:
            fields.append(DestField(
                collection=collection,
                path=col["path"],
                type=col["type"],
                ref=col.get("ref"),
                comment=col.get("comment"),
            ))
    return fields


def source_tables() -> list[str]:
    return list(SOURCE_SCHEMA["tables"].keys())


def dest_collections() -> list[str]:
    return list(DEST_SCHEMA["collections"].keys())


def fields_for_table(table: str) -> list[SourceField]:
    return [f for f in load_source_fields() if f.table == table]


def fields_for_collection(collection: str) -> list[DestField]:
    return [f for f in load_dest_fields() if f.collection == collection]
