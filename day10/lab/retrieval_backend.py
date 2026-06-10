from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent
CLEAN_DIR = ROOT / "artifacts" / "cleaned"


def _normalize_text(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text or "")
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def _tokenize(text: str) -> set[str]:
    return set(_normalize_text(text).split())


def _latest_cleaned_csv() -> Path:
    candidates = sorted(CLEAN_DIR.glob("cleaned_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError("No cleaned CSV found under artifacts/cleaned")
    return candidates[0]


def load_cleaned_rows(path: Path | None = None) -> List[Dict[str, str]]:
    target = path or _latest_cleaned_csv()
    with target.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@dataclass
class LocalKeywordCollection:
    rows: List[Dict[str, str]]

    def query(self, *, query_texts: List[str], n_results: int) -> Dict[str, List[List[Any]]]:
        all_docs: List[List[str]] = []
        all_metas: List[List[Dict[str, str]]] = []
        for query in query_texts:
            q_norm = _normalize_text(query)
            q_tokens = _tokenize(query)
            scored = []
            for row in self.rows:
                doc = row.get("chunk_text", "")
                d_norm = _normalize_text(doc)
                d_tokens = _tokenize(doc)
                overlap = len(q_tokens & d_tokens)
                number_bonus = sum(2 for token in q_tokens if token.isdigit() and token in d_tokens)
                phrase_bonus = 3 if q_norm and q_norm in d_norm else 0
                score = overlap + number_bonus + phrase_bonus
                if score > 0:
                    scored.append((score, len(doc), row))
            scored.sort(key=lambda item: (-item[0], item[1], item[2].get("doc_id", ""), item[2].get("chunk_id", "")))
            top_rows = [item[2] for item in scored[:n_results]]
            all_docs.append([row.get("chunk_text", "") for row in top_rows])
            all_metas.append(
                [
                    {
                        "doc_id": row.get("doc_id", ""),
                        "effective_date": row.get("effective_date", ""),
                    }
                    for row in top_rows
                ]
            )
        return {"documents": all_docs, "metadatas": all_metas}


def get_query_collection() -> tuple[Any, str]:
    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        chromadb = None
        embedding_functions = None

    if chromadb is not None and embedding_functions is not None:
        import os

        db_path = os.environ.get("CHROMA_DB_PATH", str(ROOT / "chroma_db"))
        collection_name = os.environ.get("CHROMA_COLLECTION", "day10_kb")
        model_name = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        try:
            client = chromadb.PersistentClient(path=db_path)
            emb = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)
            col = client.get_collection(name=collection_name, embedding_function=emb)
            return col, "chroma"
        except Exception:
            pass

    return LocalKeywordCollection(load_cleaned_rows()), "local_csv_fallback"
