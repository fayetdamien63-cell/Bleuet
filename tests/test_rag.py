from pathlib import Path

from bleuet.rag.store import KnowledgeStore, _to_fts_query

DOCS = Path(__file__).resolve().parents[1] / "data" / "knowledge"


def test_index_et_recherche(tmp_path):
    store = KnowledgeStore(tmp_path / "rag.sqlite3", DOCS)
    assert store.index() > 0
    chunks = store.search("Comment inscrire Léa à la cantine ?", top_k=2)
    assert chunks
    assert any("cantine" in chunk.text.lower() for chunk in chunks)


def test_recherche_insensible_aux_accents(tmp_path):
    store = KnowledgeStore(tmp_path / "rag.sqlite3", DOCS)
    store.index()
    assert store.search("horaires de l'ecole", top_k=2)


def test_requete_vide_si_que_des_mots_vides():
    assert _to_fts_query("est-ce que il a le") == ""
