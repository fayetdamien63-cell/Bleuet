"""Orchestrateur : assemble contexte + question -> Claude -> texte de réponse.

C'est le seul module qui connaît toutes les briques. Il ne touche jamais
directement au micro ni au haut-parleur : c'est ce qui permettra de le faire
tourner sur le serveur pendant que le Pi garde wake word + audio.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ..config import Config
from ..context.calendar_provider import build_calendar_provider
from ..context.schedules import build_schedule_store
from ..context.weather import build_weather_provider
from ..logging_setup import get_logger
from ..rag.store import build_knowledge_store
from .claude_client import build_claude_client
from .prompt import build_system_prompt

log = get_logger("bleuet.pipeline")


@dataclass
class Answer:
    question: str
    text: str
    context: str


class Orchestrator:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.weather = build_weather_provider(cfg)
        self.calendar = build_calendar_provider(cfg)
        self.schedules = build_schedule_store(cfg)
        self.knowledge = build_knowledge_store(cfg) if cfg.get("rag.enabled", True) else None
        self.claude = build_claude_client(cfg)

    def answer(self, question: str, now: dt.datetime | None = None) -> Answer:
        log.info("question : %r", question)
        stable, context = build_system_prompt(
            question,
            weather=self.weather,
            calendar=self.calendar,
            schedules=self.schedules,
            knowledge=self.knowledge,
            top_k=self.cfg.get("rag.top_k", 3),
            now=now,
        )
        text = self.claude.ask(question, stable, context)
        log.info("réponse : %r", text)
        return Answer(question=question, text=text, context=context)
