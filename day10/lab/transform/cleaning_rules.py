"""
Cleaning rules - raw export -> cleaned rows + quarantine.

Baseline gom cac failure mode mo rong (allowlist doc_id, parse ngay, HR stale version).
Sinh vien them >=3 rule moi: moi rule phai ghi `metric_impact` (xem README - chong trivial).
"""

from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Khop export hop le trong lab (mo rong khi nhom them doc moi - phai dong bo contract).
ALLOWED_DOC_IDS = frozenset(
    {
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
        "access_control_sop",
    }
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_SLASH = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_NOISY_PREFIX = "noi dung khong ro rang:"


def _norm_text(s: str) -> str:
    folded = unicodedata.normalize("NFKD", (s or "").strip())
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_only.split()).lower()


def _stable_chunk_id(doc_id: str, chunk_text: str, seq: int) -> str:
    h = hashlib.sha256(f"{doc_id}|{chunk_text}|{seq}".encode("utf-8")).hexdigest()[:16]
    return f"{doc_id}_{seq}_{h}"


def _has_repeated_sentence_burst(text: str) -> bool:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if p.strip()]
    return len(parts) >= 3 and len(set(parts)) == 1


def _normalize_effective_date(raw: str) -> Tuple[str, str]:
    """
    Tra ve (iso_date, error_reason).
    iso_date rong neu khong parse duoc.
    """
    s = (raw or "").strip()
    if not s:
        return "", "empty_effective_date"
    if _ISO_DATE.match(s):
        return s, ""
    m = _DMY_SLASH.match(s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mm}-{dd}", ""
    return "", "invalid_effective_date_format"


def load_raw_csv(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows


def clean_rows(
    rows: List[Dict[str, str]],
    *,
    apply_refund_window_fix: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Tra ve (cleaned, quarantine).

    Baseline + mo rong:
    1) Quarantine: doc_id khong thuoc allowlist.
    2) Chuan hoa effective_date sang YYYY-MM-DD; quarantine neu khong parse duoc.
    3) Quarantine: HR co effective_date < 2026-01-01.
    4) Quarantine: chunk_text rong.
    5) Strip prefix noise "Noi dung khong ro rang:" neu co.
    6) Quarantine: repeated sentence burst (mot cau lap lai >=3 lan).
    7) Quarantine: HR stale text van noi "10 ngay phep nam" / "ban HR 2025".
    8) Loai trung noi dung chunk_text (giu ban dau).
    9) Fix stale refund: 14 -> 7 ngay lam viec.
    """
    quarantine: List[Dict[str, Any]] = []
    seen_text: set[str] = set()
    cleaned: List[Dict[str, Any]] = []
    seq = 0

    for raw in rows:
        doc_id = raw.get("doc_id", "")
        text = raw.get("chunk_text", "")
        eff_raw = raw.get("effective_date", "")
        exported_at = raw.get("exported_at", "")

        if doc_id not in ALLOWED_DOC_IDS:
            quarantine.append({**raw, "reason": "unknown_doc_id"})
            continue

        eff_norm, eff_err = _normalize_effective_date(eff_raw)
        if eff_err == "empty_effective_date":
            quarantine.append({**raw, "reason": "missing_effective_date"})
            continue
        if eff_err == "invalid_effective_date_format":
            quarantine.append({**raw, "reason": eff_err, "effective_date_raw": eff_raw})
            continue

        if doc_id == "hr_leave_policy" and eff_norm < "2026-01-01":
            quarantine.append(
                {
                    **raw,
                    "reason": "stale_hr_policy_effective_date",
                    "effective_date_normalized": eff_norm,
                }
            )
            continue

        if not text:
            quarantine.append({**raw, "reason": "missing_chunk_text"})
            continue

        fixed_text = text.strip()
        norm_fixed = _norm_text(fixed_text)

        if norm_fixed.startswith(_NOISY_PREFIX):
            fixed_text = fixed_text.split(":", 1)[1].strip()
            if not fixed_text:
                quarantine.append({**raw, "reason": "noise_only_chunk_text"})
                continue
            norm_fixed = _norm_text(fixed_text)

        if _has_repeated_sentence_burst(fixed_text):
            quarantine.append({**raw, "reason": "repeated_sentence_burst"})
            continue

        if doc_id == "hr_leave_policy" and (
            "10 ngay phep nam" in norm_fixed or "ban hr 2025" in norm_fixed
        ):
            quarantine.append(
                {
                    **raw,
                    "reason": "stale_hr_policy_text",
                    "effective_date_normalized": eff_norm,
                }
            )
            continue

        if key := norm_fixed:
            if key in seen_text:
                quarantine.append({**raw, "reason": "duplicate_chunk_text"})
                continue
            seen_text.add(key)

        if apply_refund_window_fix and doc_id == "policy_refund_v4":
            if "14 ngày làm việc" in fixed_text:
                fixed_text = fixed_text.replace(
                    "14 ngày làm việc",
                    "7 ngày làm việc",
                )
                fixed_text += " [cleaned: stale_refund_window]"

        seq += 1
        cleaned.append(
            {
                "chunk_id": _stable_chunk_id(doc_id, fixed_text, seq),
                "doc_id": doc_id,
                "chunk_text": fixed_text,
                "effective_date": eff_norm,
                "exported_at": exported_at or "",
            }
        )

    return cleaned, quarantine


def write_cleaned_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at\n", encoding="utf-8")
        return
    fieldnames = ["chunk_id", "doc_id", "chunk_text", "effective_date", "exported_at"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_quarantine_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at,reason\n", encoding="utf-8")
        return
    keys: List[str] = []
    seen_k: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen_k:
                seen_k.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)
