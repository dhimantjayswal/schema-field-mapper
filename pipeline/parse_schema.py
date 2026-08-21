"""Stage 0 — normalize the two hand-transcribed schema literals into
canonical field records with description strings ready for embedding.
"""
from dataclasses import dataclass
from typing import Optional

from data.dest_schema import DEST_SCHEMA
from data.source_schema import SOURCE_SCHEMA


@dataclass(frozen=True)
class SourceField:
    """One column of one MySQL table from `data.source_schema.SOURCE_SCHEMA`.

    Example:
        >>> f = SourceField(table="emp_master", field="rec_stat", type="CHAR(1)",
        ...                 comment="A=Active, I=Inactive, T=Terminated")
        >>> f.role
        'enum_code'
        >>> f.description
        'emp_master.rec_stat — CHAR(1) — role: enum_code — A=Active, I=Inactive, T=Terminated'
    """

    table: str
    field: str
    type: str
    pk: bool = False
    fk: Optional[str] = None
    unique: bool = False
    nullable: bool = True
    comment: Optional[str] = None

    @property
    def role(self) -> str:
        """Structural role from `pipeline.roles.classify_role` — e.g. this
        is what tells `hire_dt` (timestamp_business) apart from
        `created_ts` (timestamp_audit) when both are DATETIME.
        """
        from pipeline.roles import classify_role
        return classify_role(self.field, self.type, self.comment, pk=self.pk, fk=self.fk)

    @property
    def description(self) -> str:
        """Human-readable text embedded (Stage 3) and shown to the LLM
        (Stage 4) — includes the PK/FK/role/comment context that carries
        most of the field's semantic signal.
        """
        bits = [f"{self.table}.{self.field}", self.type]
        if self.pk:
            bits.append("PRIMARY KEY")
        if self.fk:
            bits.append(f"FK -> {self.fk}")
        bits.append(f"role: {self.role}")
        if self.comment:
            bits.append(self.comment)
        return " — ".join(bits)


@dataclass(frozen=True)
class DestField:
    """One field of one MongoDB collection from `data.dest_schema.DEST_SCHEMA`.

    `path` is already dot-notation for nested fields (e.g.
    `"employment.isRemote"`) — see `data/dest_schema.py` for why the
    nesting is flattened by hand at data-entry time rather than at runtime.

    Example:
        >>> f = DestField(collection="employees", path="employment.managerId",
        ...               type="ObjectId", ref="employees._id")
        >>> f.role
        'foreign_key'
        >>> f.description
        'employees.employment.managerId — ObjectId — role: foreign_key — ref -> employees._id'
    """

    collection: str
    path: str
    type: str
    ref: Optional[str] = None
    comment: Optional[str] = None

    @property
    def role(self) -> str:
        """Structural role from `pipeline.roles.classify_role`, computed
        from this field's last path segment (`ref` doubles as the
        foreign-key signal on this side)."""
        from pipeline.roles import classify_role
        return classify_role(self.path.rsplit(".", 1)[-1], self.type, self.comment, fk=self.ref)

    @property
    def description(self) -> str:
        """Human-readable text embedded (Stage 3) and shown to the LLM
        (Stage 4) — mirrors `SourceField.description`'s shape so both
        sides read the same way in a prompt.
        """
        bits = [f"{self.collection}.{self.path}", self.type]
        bits.append(f"role: {self.role}")
        if self.ref:
            bits.append(f"ref -> {self.ref}")
        if self.comment:
            bits.append(self.comment)
        return " — ".join(bits)


def load_source_fields() -> list[SourceField]:
    """All 34 MySQL columns across all 3 source tables, as `SourceField`s.

    Recomputed from `SOURCE_SCHEMA` on every call rather than cached — the
    schema is ~34 small dict literals, so re-walking it is nowhere near
    worth adding cache invalidation for.

    Example:
        >>> len(load_source_fields())
        34
    """
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
    """All 40 MongoDB fields across all 3 destination collections, as
    `DestField`s (nested fields already flattened to dot-paths).

    Example:
        >>> len(load_dest_fields())
        40
    """
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
    """Source table names, in schema-definition order.

    Example:
        >>> source_tables()
        ['emp_master', 'dept_info', 'locations']
    """
    return list(SOURCE_SCHEMA["tables"].keys())


def dest_collections() -> list[str]:
    """Destination collection names, in schema-definition order.

    Example:
        >>> dest_collections()
        ['employees', 'departments', 'locations']
    """
    return list(DEST_SCHEMA["collections"].keys())


def fields_for_table(table: str) -> list[SourceField]:
    """All fields of one source table.

    Args:
        table: A name from `source_tables()`, e.g. "emp_master".

    Example:
        >>> len(fields_for_table("dept_info"))
        7
    """
    return [f for f in load_source_fields() if f.table == table]


def fields_for_collection(collection: str) -> list[DestField]:
    """All fields of one destination collection.

    Args:
        collection: A name from `dest_collections()`, e.g. "departments".

    Example:
        >>> len(fields_for_collection("departments"))
        7
    """
    return [f for f in load_dest_fields() if f.collection == collection]
