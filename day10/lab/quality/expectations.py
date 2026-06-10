"""
Expectation suite don gian (khong bat buoc Great Expectations).

Sinh vien co the thay bang GE / pydantic / custom - mien la co halt co kiem soat.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

REQUIRED_DOC_IDS = frozenset(
    {
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
        "access_control_sop",
    }
)


@dataclass
class ExpectationResult:
    name: str
    passed: bool
    severity: str  # "warn" | "halt"
    detail: str


def _has_repeated_sentence_burst(text: str) -> bool:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if p.strip()]
    return len(parts) >= 3 and len(set(parts)) == 1


def run_expectations(cleaned_rows: List[Dict[str, Any]]) -> Tuple[List[ExpectationResult], bool]:
    """
    Tra ve (results, should_halt).

    should_halt = True neu co bat ky expectation severity halt nao fail.
    """
    results: List[ExpectationResult] = []

    ok = len(cleaned_rows) >= 1
    results.append(
        ExpectationResult(
            "min_one_row",
            ok,
            "halt",
            f"cleaned_rows={len(cleaned_rows)}",
        )
    )

    bad_doc = [r for r in cleaned_rows if not (r.get("doc_id") or "").strip()]
    ok2 = len(bad_doc) == 0
    results.append(
        ExpectationResult(
            "no_empty_doc_id",
            ok2,
            "halt",
            f"empty_doc_id_count={len(bad_doc)}",
        )
    )

    bad_refund = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "policy_refund_v4"
        and "14 ngày làm việc" in (r.get("chunk_text") or "")
    ]
    ok3 = len(bad_refund) == 0
    results.append(
        ExpectationResult(
            "refund_no_stale_14d_window",
            ok3,
            "halt",
            f"violations={len(bad_refund)}",
        )
    )

    short = [r for r in cleaned_rows if len((r.get("chunk_text") or "")) < 8]
    ok4 = len(short) == 0
    results.append(
        ExpectationResult(
            "chunk_min_length_8",
            ok4,
            "warn",
            f"short_chunks={len(short)}",
        )
    )

    iso_bad = [
        r
        for r in cleaned_rows
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", (r.get("effective_date") or "").strip())
    ]
    ok5 = len(iso_bad) == 0
    results.append(
        ExpectationResult(
            "effective_date_iso_yyyy_mm_dd",
            ok5,
            "halt",
            f"non_iso_rows={len(iso_bad)}",
        )
    )

    bad_hr_annual = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "hr_leave_policy"
        and "10 ngày phép năm" in (r.get("chunk_text") or "")
    ]
    ok6 = len(bad_hr_annual) == 0
    results.append(
        ExpectationResult(
            "hr_leave_no_stale_10d_annual",
            ok6,
            "halt",
            f"violations={len(bad_hr_annual)}",
        )
    )

    present_doc_ids = {r.get("doc_id", "").strip() for r in cleaned_rows if (r.get("doc_id") or "").strip()}
    missing_doc_ids = sorted(REQUIRED_DOC_IDS - present_doc_ids)
    ok7 = not missing_doc_ids
    results.append(
        ExpectationResult(
            "required_doc_coverage",
            ok7,
            "halt",
            f"missing={missing_doc_ids}",
        )
    )

    repeated = [r for r in cleaned_rows if _has_repeated_sentence_burst(r.get("chunk_text", ""))]
    ok8 = len(repeated) == 0
    results.append(
        ExpectationResult(
            "no_repeated_sentence_burst",
            ok8,
            "warn",
            f"violations={len(repeated)}",
        )
    )

    halt = any(not r.passed and r.severity == "halt" for r in results)
    return results, halt
