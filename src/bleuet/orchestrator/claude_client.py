"""Appel à l'API Claude (SDK anthropic)."""

from __future__ import annotations

import os
import time

from ..logging_setup import get_logger

log = get_logger("bleuet.claude")


class ClaudeClient:
    def __init__(
        self,
        model: str = "claude-opus-5",
        max_tokens: int = 800,
        effort: str = "low",
        timeout: float = 30.0,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        self.timeout = timeout
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        import anthropic

        if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            log.warning(
                "ANTHROPIC_API_KEY n'est pas définie ; le SDK tentera un profil "
                "`ant auth login` s'il en existe un."
            )
        self._client = anthropic.Anthropic(timeout=self.timeout)
        return self._client

    def ask(self, question: str, system_stable: str, system_context: str) -> str:
        """Une question, une réponse. Pas d'historique : chaque interaction
        vocale est indépendante (à faire évoluer si on veut le suivi de
        conversation)."""
        import anthropic

        client = self._get_client()
        started = time.monotonic()
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                # `effort: low` garde la latence basse : c'est ce qui compte pour
                # une réponse parlée. Passe à "high" si les réponses te semblent
                # trop superficielles.
                output_config={"effort": self.effort},
                system=[
                    # Bloc figé -> mis en cache par l'API entre les questions.
                    {
                        "type": "text",
                        "text": system_stable,
                        "cache_control": {"type": "ephemeral"},
                    },
                    # Bloc du jour (météo, agenda, RAG) -> change à chaque question.
                    {"type": "text", "text": system_context},
                ],
                messages=[{"role": "user", "content": question}],
            )
        except anthropic.APIStatusError as exc:
            log.error("erreur API Claude (%s) : %s", exc.status_code, exc)
            raise
        except anthropic.APIConnectionError as exc:
            log.error("connexion à l'API Claude impossible : %s", exc)
            raise

        if response.stop_reason == "refusal":
            log.warning("réponse refusée par le modèle : %s", response.stop_details)
            return "Je préfère ne pas répondre à cette question."

        text = "".join(block.text for block in response.content if block.type == "text").strip()
        usage = response.usage
        log.info(
            "réponse Claude en %.1f s (entrée %d tok, cache %d tok, sortie %d tok)",
            time.monotonic() - started,
            usage.input_tokens,
            getattr(usage, "cache_read_input_tokens", 0) or 0,
            usage.output_tokens,
        )
        return text


def build_claude_client(cfg) -> ClaudeClient:
    return ClaudeClient(
        model=cfg.get("llm.model", "claude-opus-5"),
        max_tokens=cfg.get("llm.max_tokens", 800),
        effort=cfg.get("llm.effort", "low"),
        timeout=cfg.get("llm.timeout", 30.0),
    )
