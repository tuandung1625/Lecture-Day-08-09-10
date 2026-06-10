#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from dotenv import load_dotenv

from retrieval_backend import ROOT, get_query_collection

load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--questions",
        default=str(ROOT / "data" / "test_questions.json"),
        help="JSON danh sach cau hoi golden",
    )
    parser.add_argument(
        "--out",
        default=str(ROOT / "artifacts" / "eval" / "before_after_eval.csv"),
        help="CSV ket qua",
    )
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    qpath = Path(args.questions)
    if not qpath.is_file():
        raise SystemExit(f"questions not found: {qpath}")

    questions = json.loads(qpath.read_text(encoding="utf-8"))
    col, backend = get_query_collection()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "question_id",
        "question",
        "top1_doc_id",
        "top1_preview",
        "contains_expected",
        "hits_forbidden",
        "top1_doc_expected",
        "top_k_used",
        "backend",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as fcsv:
        w = csv.DictWriter(fcsv, fieldnames=fieldnames)
        w.writeheader()
        for q in questions:
            text = q["question"]
            res = col.query(query_texts=[text], n_results=args.top_k)
            docs = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            top_doc = (metas[0] or {}).get("doc_id", "") if metas else ""
            preview = (docs[0] or "")[:180].replace("\n", " ") if docs else ""
            blob = " ".join(docs).lower()
            must_any = [x.lower() for x in q.get("must_contain_any", [])]
            forbidden = [x.lower() for x in q.get("must_not_contain", [])]
            ok_any = any(m in blob for m in must_any) if must_any else True
            bad_forb = any(m in blob for m in forbidden) if forbidden else False
            want_top1 = (q.get("expect_top1_doc_id") or "").strip()
            top1_expected = ""
            if want_top1:
                top1_expected = "yes" if top_doc == want_top1 else "no"
            w.writerow(
                {
                    "question_id": q.get("id", ""),
                    "question": text,
                    "top1_doc_id": top_doc,
                    "top1_preview": preview,
                    "contains_expected": "yes" if ok_any else "no",
                    "hits_forbidden": "yes" if bad_forb else "no",
                    "top1_doc_expected": top1_expected,
                    "top_k_used": args.top_k,
                    "backend": backend,
                }
            )

    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
