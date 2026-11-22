"""Pydantic models: the source of truth for every file an agent writes (07-building, Files, not a database).

Every model forbids unknown keys. Nothing a rule computes is a field here: no
statuses, verdicts, matches, contrasts or resolved contexts.
"""
from __future__ import annotations

import re
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ID = re.compile(r"^[A-Za-z0-9_]+$")


def check_id(s: str, what: str) -> str:
    if not ID.match(s):
        raise ValueError(f"{what} id {s!r} must match [A-Za-z0-9_]+ (no dots, spaces or slashes) (02-audit, Ids)")
    return s


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ shared
class Anchor(Strict):
    quote: str
    where: str
    file: str | None = None
    kind: Literal["text", "table cell", "dataset cell", "figure text", "unit"] = "text"


class SuspectedError(Strict):
    what: str
    why: str


class DataPointer(Strict):
    file: str
    sheet: str | None = None
    cells: str


class ByReference(Strict):
    citation: str
    anchor: Anchor


# ------------------------------------------------------------------ record (02-audit)
class ContextObj(Strict):
    value: str | None = None
    qualifiers: dict[str, str] = Field(default_factory=dict)
    note: str | None = None
    by_reference: ByReference | None = None
    suspected_error: SuspectedError | None = None
    anchor: Anchor | None = None

    @model_validator(mode="after")
    def _one(self):
        if (self.value is None) == (self.by_reference is None):
            raise ValueError("a context value is either `value` or `by_reference`")
        return self


class ContextAnchor(Strict):
    """One anchor per distinct stated context value (02-audit, Context is anchored too)."""
    field: str  # a field, or field.qualifier for a qualifier's value
    value: str  # the stated wording, exactly as written in the record
    anchor: Anchor


class Removal(Strict):
    """An id a re-read drops on purpose, with its reason (07-building, Reviewing agent reports)."""
    id: str
    why: str


class OtherCondition(Strict):
    """A stated condition no field holds: quoted, checked, never mapped (03-vocabulary, Fields are designed from the corpus)."""
    text: str
    anchor: Anchor


ContextValue = Union[str, ContextObj]
Context = dict[str, ContextValue]


def stated_text(v: ContextValue) -> str | None:
    if isinstance(v, str):
        return v
    return v.value


class NotUsed(Strict):
    """A file in the paper's folder that holds no values for this record, and what it holds (02-audit)."""
    file: str
    why: str


class Source(Strict):
    title: str
    doi: str | None = None
    year: str
    first_author: str | None = None
    last_author: str | None = None
    lab: str | None = None
    journal: str | None = None
    files: list[str]
    missing: list[str] = Field(default_factory=list)  # supplements or source data the paper names that are not in its folder
    not_used: list[NotUsed] = Field(default_factory=list)  # files in the folder read and found to hold no values
    version_note: str | None = None


GroupKind = Literal["engineered", "native tissue", "other study", "wild type", "perturbed", "natural"]
BENCHMARK_KINDS = ("native tissue", "other study")


class Group(Strict):
    label: str
    kind: GroupKind = "engineered"
    context: Context = Field(default_factory=dict)
    citation: str | None = None  # another study's data, with its citation
    anchor: Anchor | None = None
    note: str | None = None
    other_conditions: list[OtherCondition] = Field(default_factory=list)

    @model_validator(mode="after")
    def _cite(self):
        if self.kind == "other study" and not self.citation:
            raise ValueError("an other-study group carries its citation (02-audit, Groups)")
        return self

    @property
    def benchmark(self) -> bool:
        return self.kind in BENCHMARK_KINDS


class Unit(Strict):
    where: str
    title: str
    context: Context = Field(default_factory=dict)
    groups: dict[str, Group] = Field(default_factory=dict)
    anchor: Anchor | None = None
    note: str | None = None
    other_conditions: list[OtherCondition] = Field(default_factory=list)

    @field_validator("groups")
    @classmethod
    def _gids(cls, v):
        for k in v:
            check_id(k, "group")
        return v


class N(Strict):
    printed: str
    counts: str
    per_group: dict[str, str] | None = None
    levels: dict[str, int] | None = None
    test_unit: str | None = None
    origin: Literal["stated", "from data"] = "stated"
    data: DataPointer | None = None


Spread = Literal["SD", "SEM", "CI95", "range", "IQR", "not stated", "none"]


ValueKind = Literal["mean", "median", "value", "difference", "ratio", "percent", "fraction", "sd", "sem", "n", "count"]


class Value(Strict):
    printed: str
    unit: str
    kind: ValueKind = "mean"
    group: str | None = None
    between: list[str] | None = None
    over: list[str] | None = None  # a value or range printed for several groups at once
    x: str | None = None
    expressed_as: Literal["absolute", "% of baseline", "% change", "fold", "normalised"] | None = None  # from its legend
    normalised_to: str | None = None  # what the value is divided by, as printed
    spread: Spread = "not stated"
    spread_source: Literal["sentence", "legend", "methods"] | None = None
    origin: Literal["stated", "from data"] = "stated"
    data: DataPointer | None = None
    suspected_error: SuspectedError | None = None

    @model_validator(mode="after")
    def _attach(self):
        if sum(x is not None for x in (self.group, self.between, self.over)) > 1:
            raise ValueError("a value attaches to one group, or carries `between: [a, b]`, or `over: [groups]`; "
                             "only one of them")
        if self.over is not None and len(self.over) < 2:
            raise ValueError("`over` names at least two groups")
        if self.between is not None and len(self.between) != 2:
            raise ValueError("`between` names exactly two groups")
        return self


class PrintedP(Strict):
    p: str
    anchor: Anchor


class Stats(Strict):
    test: str = "not stated"
    statistic: str = "not stated"
    df: str | None = None
    p: str = "not stated"
    p_values: list[PrintedP] = Field(default_factory=list)  # further printed P for the same test, each anchored


class Sides(Strict):
    condition: list[str]
    reference: list[str]


class StatedDirection(Strict):
    direction: Literal["up", "down", "none"]
    anchor: Anchor


class ScalingLaw(Strict):
    independent_measure: str
    direction: Literal["up", "down", "none"]
    stratified_by: str | None = None
    anchor: Anchor


TestOf = Literal["pair", "omnibus", "main effect", "interaction"]


class Item(Strict):
    unit: str
    measure: str
    method: str | None = None
    software: str | None = None
    definition: Union[str, ByReference] = "not stated"
    finding: str
    groups: list[str] | None = None
    compares: Union[list[str], Sides, None] = None
    test_of: TestOf | None = None
    context: Context = Field(default_factory=dict)
    n: Union[N, Literal["not stated"]] = "not stated"
    values: dict[str, Value] = Field(default_factory=dict)
    stats: Stats = Field(default_factory=Stats)
    anchor: Anchor
    stated_direction: StatedDirection | None = None
    scaling: ScalingLaw | None = None
    suspected_error: SuspectedError | None = None
    note: str | None = None

    @field_validator("values")
    @classmethod
    def _vnames(cls, v):
        for k in v:
            check_id(k, "value")
        return v

    @model_validator(mode="after")
    def _form(self):
        if self.groups is not None and self.compares is not None:
            raise ValueError("an item has `groups` (a measurement) or `compares` (a test), not both")
        if isinstance(self.compares, Sides):
            if self.test_of != "main effect":
                raise ValueError("`compares: {condition, reference}` needs `test_of: main effect`")
        elif isinstance(self.compares, list):
            if len(self.compares) < 2:
                raise ValueError("`compares` names at least two groups")
            if len(self.compares) == 2 and self.test_of not in (None, "pair", "interaction"):
                raise ValueError("two compared groups are a pair")
            if len(self.compares) > 2 and self.test_of not in ("omnibus", "interaction"):
                raise ValueError("more than two compared groups need `test_of: omnibus` or `interaction`")
        elif self.test_of is not None:
            raise ValueError("`test_of` needs `compares`")
        return self

    @property
    def kind_of_test(self) -> str | None:
        if self.compares is None:
            return None
        if isinstance(self.compares, Sides):
            return "main effect"
        return self.test_of or "pair"

    def group_ids(self) -> list[str]:
        if self.groups:
            return list(self.groups)
        if isinstance(self.compares, Sides):
            return list(self.compares.condition) + list(self.compares.reference)
        return list(self.compares or [])


Judgement = Literal["follows", "overstated", "does not follow", "cannot judge"]
DIMENSIONS = ("direction", "support", "comparison", "scope", "replication", "strength", "presence")
VERDICT_ORDER = ("does not follow", "overstated", "cannot judge", "follows")


class Claim(Strict):
    kind: Literal["stated", "attributed", "literature"]
    quote: str
    where: str
    scope: str = "not stated"
    direction: str = "not stated"
    asserts_direction: Literal["up", "down", "none"] | None = None  # what the claim asserts of the items it rests on
    strength: str = "not stated"
    rests_on: list[str] = Field(default_factory=list)
    opposes: list[str] = Field(default_factory=list)
    restates: str | None = None
    cites: list[str] = Field(default_factory=list)
    judgement: dict[str, Judgement] | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _dims(self):
        if self.judgement is not None and set(self.judgement) != set(DIMENSIONS):
            raise ValueError(f"judgement needs exactly the dimensions {DIMENSIONS}")
        if self.kind == "stated" and self.judgement is None:
            raise ValueError("a stated claim is judged on every dimension")
        return self


def claim_verdict(c: Claim) -> str | None:
    """The worst dimension: does not follow > overstated > cannot judge > follows (02-audit)."""
    if c.judgement is None:
        return None
    return min(c.judgement.values(), key=VERDICT_ORDER.index)


Purpose = Literal["attributes_finding", "borrows_method", "borrows_value", "borrows_data", "contrasts"]


class Citation(Strict):
    label: str
    text: str
    doi: str | None = None
    year: str | None = None
    purpose: list[Purpose]
    anchor: Anchor


class CrossReference(Strict):
    cited: str
    shows: str
    anchor: Anchor


class Record(Strict):
    id: str
    field_set: int = 1  # the field set the record was read against; later fields are 'not yet read'
    context_anchors: list[ContextAnchor] = Field(default_factory=list)  # required from field set 3
    removed: list[Removal] = Field(default_factory=list)
    source: Source
    default_context: Context
    units: dict[str, Unit]
    evidence: dict[str, Item]
    claims: dict[str, Claim] = Field(default_factory=dict)
    citations: dict[str, Citation] = Field(default_factory=dict)
    cross_references: list[CrossReference] = Field(default_factory=list)

    @field_validator("units", "evidence", "claims", "citations")
    @classmethod
    def _ids(cls, v):
        for k in v:
            check_id(k, "unit/item/claim/citation")
        return v


# ------------------------------------------------------------------ figures, readings, data (02-audit, Reading figures)
class GroupLink(Strict):
    item: str
    group: str
    unit_of_value: str


class FigureEntry(Strict):
    file: str
    page: int = 1
    crop: tuple[float, float, float, float]
    script: str
    unit: str
    kind: Literal["vector", "raster", "heat map", "image table", "microscopy"] = "vector"
    groups: dict[str, GroupLink]
    note: str | None = None


class FiguresFile(Strict):
    figures: dict[str, FigureEntry] = Field(default_factory=dict)
    # figure units a figure job looked at and found to plot no individual points: unit -> what it shows
    # (07-building, No needless compute); such a figure is not read and not listed again
    no_points: dict[str, str] = Field(default_factory=dict)


class Suspect(Strict):
    why: str


class Reading(Strict):
    figure: str
    group: str
    kind: Literal["point", "mean", "error", "median", "q1", "q3", "whisker_lo", "whisker_hi"]
    index: int
    value: float
    lo: float
    hi: float
    x: float | None = None
    page_x: float | None = None
    page_y: float | None = None
    suspect: Suspect | None = None  # logged by the reader; checks run with and without it


class ReadingsFile(Strict):
    readings: list[Reading] = Field(default_factory=list)


class DataValue(Strict):
    item: str
    group: str
    kind: Literal["point", "mean", "sd", "sem", "n", "p"] = "point"
    x: str | None = None
    file: str
    sheet: str | None = None
    cell: str
    value: str
    unit: str
    suspect: Suspect | None = None  # e.g. 68 among values 0.9–3.9; checks run with and without it


class DataFile(Strict):
    data: list[DataValue] = Field(default_factory=list)


# ------------------------------------------------------------------ terms.yaml (03-vocabulary)
FlagKind = Literal["placeholder", "alternatives", "several conditions", "several measures", "not a context",
                   "two fields in one"]


class Flag(Strict):
    kind: FlagKind
    note: str


class SplitRequest(Strict):
    words: str
    field: str


class Agent(Strict):
    model: str
    instructions: str
    run: str | None = None


class Mapping(Strict):
    """One distinct stated text of one field, mapped once per paper (03-vocabulary, How code matches)."""
    field: str
    stated: str
    terms: list[str] = Field(default_factory=list)
    qualifiers: dict[str, str] = Field(default_factory=dict)
    flag: Flag | None = None
    split: list[SplitRequest] = Field(default_factory=list)
    no_ontology_term: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _flag(self):
        if self.flag and self.terms:
            raise ValueError("a flagged value carries no terms")
        if not self.flag and not self.terms:
            raise ValueError("a mapping has terms or a flag")
        return self


class TermsFile(Strict):
    record: str
    vocabulary_version: int
    agent: Agent | None = None
    edits: list[dict] = Field(default_factory=list)
    mappings: list[Mapping] = Field(default_factory=list)


# ------------------------------------------------------------------ formulas (04-formulas)
class Use(Strict):
    formula: str
    subs: dict[str, str] = Field(default_factory=dict)


class FormulaTest(Strict):
    given: dict[str, float] = Field(default_factory=dict)
    expect: dict[str, float] = Field(default_factory=dict)
    does_not_apply: str | None = None


class Cites(Strict):
    text: str
    quote: str | None = None
    url: str | None = None
    anchor: Anchor | None = None  # when a paper states it


class FormulaEntry(Strict):
    formula: str
    kind: Literal["definition", "model", "bound", "derived"]
    statement: str
    equations: list[str]
    variables: dict[str, str]
    assumes: list[str] = Field(default_factory=list)
    uses: list[Use] = Field(default_factory=list)
    applies_when: dict[str, list[str]] = Field(default_factory=dict)
    does_not_apply: str | None = None
    tests: list[FormulaTest]
    cites: Cites | None = None


# ------------------------------------------------------------------ derived.yaml (04-formulas, Derivations)
class Input(Strict):
    item: str | None = None
    value: str | None = None
    part: Literal["mean", "spread"] | None = None
    printed: str | None = None
    unit: str | None = None
    anchor: Anchor | None = None
    data: str | None = None      # "<item>/<group>"
    reading: str | None = None   # "<figure>/<group>"
    x: str | None = None         # the point on a curve (dose, frequency, time) for data or reading inputs
    derived: str | None = None
    by_reference: ByReference | None = None
    not_stated: bool = False
    kind: Literal["constant", "per sample", "not stated"] = "not stated"
    note: str | None = None

    @model_validator(mode="after")
    def _one(self):
        srcs = [self.item, self.value, self.printed, self.data, self.reading, self.derived, self.by_reference]
        if sum(x is not None for x in srcs) + bool(self.not_stated) != 1:
            raise ValueError("an input points at exactly one of item, value, printed, data, reading, derived, "
                             "by_reference, or is not_stated")
        if self.printed is not None and self.anchor is None:
            raise ValueError("a printed input carries its anchor")
        return self


class LibraryRef(Strict):
    formula: str
    vars: dict[str, str]


class Alternative(Strict):
    label: str
    formula: str | None = None
    note: str | None = None


class Derivation(Strict):
    item: str
    group: str | None = None
    measure: str | None = None
    formula: str  # as stated, as an equation "s = F/A", or "not stated"
    anchor: Union[Anchor, Literal["not stated"]]
    library: LibraryRef | None = None
    no_formula: str | None = None
    inputs: dict[str, Input] = Field(default_factory=dict)
    output: str | None = None  # "<item>.values.<name>"
    output_unit: str | None = None
    alternatives: list[Alternative] = Field(default_factory=list)
    aggregation: Literal["mean of per-sample", "of means", "not stated"] | None = None  # per-sample formula vs a mean
    note: str | None = None

    @model_validator(mode="after")
    def _lib(self):
        if (self.library is None) == (self.no_formula is None):
            raise ValueError("a derivation names a library formula or gives no_formula: <reason>")
        return self


class AssumptionReport(Strict):
    model: str
    assumptions: dict[str, dict]


class Bound(Strict):
    item: str
    value: str
    formula: str


class DerivedFile(Strict):
    record: str
    formula_library_version: int
    agent: Agent | None = None
    derived: dict[str, Derivation] = Field(default_factory=dict)
    assumptions: dict[str, AssumptionReport] = Field(default_factory=dict)
    bounds: list[Bound] = Field(default_factory=list)
    proposals: list[FormulaEntry] = Field(default_factory=list)
    reason_if_empty: str | None = None


class ManifestRepo(Strict):
    kind: str
    url: str
    doi: str | None = None
    note: str | None = None


class ManifestFile(Strict):
    file: str
    role: Literal["main_text", "main_figure", "supp_text", "supp_table", "supp_figure", "raw_data", "code"]


class ManifestNotUsed(Strict):
    file: str
    why: str


class Manifest(Strict):
    """Per-paper provenance, open-access license, figure-embedding policy, and 100% file inventory."""
    id: str
    doi: str
    title: str
    year: int
    journal: str
    oa_status: Literal["open_access", "restricted"] = "open_access"
    license: str
    figure_embed_policy: Literal["public_thumbnails", "local_only"] = "public_thumbnails"
    repositories: list[ManifestRepo] = Field(default_factory=list)
    files: list[ManifestFile] = Field(default_factory=list)
    not_used: list[ManifestNotUsed] = Field(default_factory=list)

