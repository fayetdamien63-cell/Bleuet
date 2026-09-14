"""API HTTP de l'orchestrateur.

C'est la frontière Pi / serveur : le Pi détecte le wake word, enregistre, et
envoie soit du texte (POST /ask) soit un wav (POST /ask-audio) ; il récupère le
texte de la réponse et le synthétise localement avec Piper.
"""

from __future__ import annotations

import io

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..config import Config
from ..logging_setup import get_logger
from ..orchestrator.pipeline import Orchestrator
from ..stt.factory import build_transcriber

log = get_logger("bleuet.server")


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    question: str
    answer: str


def create_app(cfg: Config | None = None) -> FastAPI:
    config = cfg or Config.load()
    app = FastAPI(title="Bleuet", version="0.1.0")
    orchestrator = Orchestrator(config)
    transcriber = build_transcriber(config)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "model": config.get("llm.model")}

    @app.post("/ask", response_model=AskResponse)
    def ask(request: AskRequest) -> AskResponse:
        if not request.question.strip():
            raise HTTPException(status_code=400, detail="question vide")
        answer = orchestrator.answer(request.question)
        return AskResponse(question=answer.question, answer=answer.text)

    @app.post("/ask-audio", response_model=AskResponse)
    async def ask_audio(file: UploadFile = File(...)) -> AskResponse:
        import soundfile as sf

        raw = await file.read()
        samples, rate = sf.read(io.BytesIO(raw), dtype="float32", always_2d=False)
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        if rate != config.get("audio.sample_rate", 16000):
            raise HTTPException(
                status_code=400,
                detail=f"audio à {rate} Hz, attendu {config.get('audio.sample_rate', 16000)} Hz",
            )
        transcription = transcriber.transcribe(samples, rate)
        if not transcription.text:
            raise HTTPException(status_code=422, detail="transcription vide")
        answer = orchestrator.answer(transcription.text)
        return AskResponse(question=answer.question, answer=answer.text)

    return app


# Pour uvicorn en direct :
#   uvicorn "bleuet.server.app:create_app" --factory --host 0.0.0.0 --port 8000
