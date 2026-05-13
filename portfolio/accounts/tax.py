from __future__ import annotations

from typing import Literal

TaxTreatment = Literal["taxable", "tax-advantaged"]

_TAX_ADVANTAGED_SUBTYPES = frozenset(
    {
        "401a",
        "401k",
        "403b",
        "457b",
        "529",
        "education savings account",
        "fhsa",
        "hsa",
        "ira",
        "keogh",
        "lif",
        "lira",
        "lrsp",
        "pension",
        "profit sharing plan",
        "qshr",
        "rdsp",
        "resp",
        "retirement",
        "roth",
        "roth 401k",
        "roth 403b",
        "roth 457b",
        "roth ira",
        "roth pension",
        "roth profit sharing plan",
        "roth thrift savings plan",
        "rrsp",
        "sarsep",
        "sep ira",
        "simple ira",
        "sipp",
        "thrift savings plan",
        "tfsa",
        "ugma",
        "utma",
        "health reimbursement arrangement",
    }
)


def derive_tax_treatment(subtype: str | None) -> TaxTreatment:
    if not subtype:
        return "taxable"
    normalized = subtype.strip().lower()
    if normalized in _TAX_ADVANTAGED_SUBTYPES:
        return "tax-advantaged"
    return "taxable"
