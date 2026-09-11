from bleuet.config import Config


def test_surcharge_par_environnement(monkeypatch):
    monkeypatch.setenv("BLEUET_STT_MODEL", "tiny")
    monkeypatch.setenv("BLEUET_RAG_ENABLED", "false")
    cfg = Config.load()
    assert cfg.get("stt.model") == "tiny"
    assert cfg.get("rag.enabled") is False


def test_valeur_par_defaut_si_cle_absente():
    assert Config.load().get("llm.inexistant", "défaut") == "défaut"


def test_resolution_de_chemin():
    path = Config.load().resolve_path("rag.docs_dir")
    assert path.is_absolute() and path.name == "knowledge"
