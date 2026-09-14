"""RAG léger : SQLite FTS5 (BM25) sur les documents de `data/knowledge/`.

Pourquoi pas d'embeddings ? Un modèle d'embeddings (sentence-transformers +
torch) pèse ~2 Go d'installation et plusieurs centaines de Mo de RAM : c'est
inenvisageable sur un Pi 3 (1 Go), et inutile ici — le corpus familial fait
quelques pages et les questions reprennent le vocabulaire des documents.
FTS5 est intégré à SQLite (zéro dépendance), indexe en millisecondes, et
l'interface `Retriever` ci-dessous permet de brancher Chroma ou une API
d'embeddings plus tard sans toucher à l'orchestrateur.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ..logging_setup import get_logger

log = get_logger("bleuet.rag")

# Mots trop fréquents pour discriminer : ils ne servent qu'à diluer le score BM25.
STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "et", "ou", "a", "à",
    "au", "aux", "en", "est", "sont", "ce", "cet", "cette", "ces", "il", "elle",
    "on", "nous", "vous", "ils", "elles", "que", "qui", "quoi", "quand", "quel",
    "quelle", "quels", "quelles", "pour", "par", "sur", "dans", "avec", "sans",
    "pas", "ne", "je", "tu", "me", "te", "se", "y", "l", "s", "c", "n", "qu",
    "est-ce", "quelle_est", "comment", "pourquoi", "combien", "mon", "ma", "mes",
}


@dataclass
class Chunk:
    doc: str
    text: str
    score: float = 0.0


class KnowledgeStore:
    def __init__(self, db_path: str | Path, docs_dir: str | Path, chunk_chars: int = 700):
        self.db_path = Path(db_path)
        self.docs_dir = Path(docs_dir)
        self.chunk_chars = chunk_chars

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks "
            "USING fts5(doc, body, tokenize='unicode61 remove_diacritics 2')"
        )
        return connection

    def index(self) -> int:
        """(Ré)indexe tous les .md/.txt du dossier de connaissances."""
        if not self.docs_dir.exists():
            log.warning("dossier de connaissances absent : %s", self.docs_dir)
            return 0

        files = sorted(
            path
            for pattern in ("*.md", "*.txt")
            for path in self.docs_dir.rglob(pattern)
        )
        total = 0
        with self._connect() as connection:
            connection.execute("DELETE FROM chunks")
            for path in files:
                text = path.read_text(encoding="utf-8")
                for chunk in _split(text, self.chunk_chars):
                    connection.execute(
                        "INSERT INTO chunks (doc, body) VALUES (?, ?)", (path.name, chunk)
                    )
                    total += 1
        log.info("index RAG reconstruit : %d passage(s) depuis %d fichier(s)", total, len(files))
        return total

    def search(self, question: str, top_k: int = 3) -> list[Chunk]:
        if not self.db_path.exists():
            log.warning("index RAG absent ; lance `bleuet index`")
            return []
        query = _to_fts_query(question)
        if not query:
            return []
        with self._connect() as connection:
            try:
                rows = connection.execute(
                    "SELECT doc, body, bm25(chunks) AS score FROM chunks "
                    "WHERE chunks MATCH ? ORDER BY score LIMIT ?",
                    (query, top_k),
                ).fetchall()
            except sqlite3.OperationalError as exc:
                log.warning("requête FTS invalide (%s) : %s", query, exc)
                return []
        # bm25() renvoie un score négatif (plus proche de -inf = plus pertinent).
        results = [Chunk(doc=row[0], text=row[1], score=-row[2]) for row in rows]
        log.info(
            "RAG : %d passage(s) trouvé(s) %s",
            len(results),
            [f"{chunk.doc} ({chunk.score:.2f})" for chunk in results],
        )
        return results


def _split(text: str, chunk_chars: int) -> list[str]:
    """Découpe par paragraphes, en regroupant jusqu'à `chunk_chars`."""
    paragraphs = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > chunk_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        chunks.append(current)
    return chunks


def _to_fts_query(question: str) -> str:
    """Transforme une question en requête FTS5 `OR` tolérante aux accents."""
    normalized = unicodedata.normalize("NFD", question.lower())
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    words = [w for w in re.findall(r"[a-z0-9]+", normalized) if len(w) > 2 and w not in STOPWORDS]
    if not words:
        return ""
    # Le préfixe * rattrape les pluriels et les formes fléchies (cantine/cantines).
    return " OR ".join(f'"{word}"*' for word in dict.fromkeys(words))


def build_knowledge_store(cfg) -> KnowledgeStore:
    return KnowledgeStore(
        db_path=cfg.resolve_path("rag.db_path", "data/rag.sqlite3"),
        docs_dir=cfg.resolve_path("rag.docs_dir", "data/knowledge"),
        chunk_chars=cfg.get("rag.chunk_chars", 700),
    )
