"""Construction du prompt système : instructions + données du jour + RAG."""

from __future__ import annotations

import datetime as dt

from ..context.calendar_provider import CalendarProvider
from ..context.schedules import ScheduleStore
from ..context.weather import WeatherProvider
from ..logging_setup import get_logger
from ..rag.store import KnowledgeStore

log = get_logger("bleuet.prompt")

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]

# Partie stable du prompt : elle ne change jamais d'une question à l'autre, ce
# qui la rend cachable côté API (voir cache_control dans claude_client.py).
INSTRUCTIONS = """\
Tu es Bleuet, l'assistant vocal d'une famille. Tu réponds à voix haute, via une \
synthèse vocale : ta réponse est LUE, pas lue à l'écran.

Règles de forme (impératives) :
- Réponds en français, en 1 à 3 phrases courtes. Jamais de liste à puces, de \
titre, de tableau, de markdown, d'emoji ni d'URL : tout cela s'entend mal.
- Écris les heures en toutes lettres parlées : « huit heures trente », pas « 08:30 ».
- Va droit au but : pas de formule d'accueil, pas de « bien sûr », pas de \
reformulation de la question.

Règles de fond :
- Appuie-toi UNIQUEMENT sur les informations du contexte ci-dessous et sur la \
question. Si l'information n'y est pas, dis-le simplement en une phrase \
(« Je n'ai pas cette information ») et propose, si c'est pertinent, où la trouver.
- N'invente jamais un horaire, une date ou un nom.
- Si la question est ambiguë, pose une seule question de clarification, courte.
- Tu ne peux pas agir sur le monde : tu ne peux ni envoyer de message, ni \
modifier l'agenda, ni commander d'objet. Si on te le demande, dis-le en une phrase.
"""


def french_date(day: dt.date) -> str:
    return f"{JOURS[day.weekday()]} {day.day} {MOIS[day.month - 1]} {day.year}"


def build_system_prompt(
    question: str,
    *,
    weather: WeatherProvider | None = None,
    calendar: CalendarProvider | None = None,
    schedules: ScheduleStore | None = None,
    knowledge: KnowledgeStore | None = None,
    top_k: int = 3,
    now: dt.datetime | None = None,
) -> tuple[str, str]:
    """Retourne (partie_stable, partie_variable) du prompt système.

    La séparation sert au cache de prompt : seule la seconde partie change.
    """
    moment = now or dt.datetime.now()
    today = moment.date()
    blocks: list[str] = [
        f"# Date et heure\nNous sommes le {french_date(today)}, il est "
        f"{moment.hour} h {moment.minute:02d}."
    ]

    if weather is not None:
        current = weather.current()
        blocks.append(
            "# Météo du jour\n" + (current.to_text() if current else "Non disponible.")
        )

    if calendar is not None:
        events = calendar.events_for_day(today)
        body = "\n".join(f"- {event.to_text()}" for event in events) or "Rien de prévu."
        blocks.append(f"# Agenda familial du jour\n{body}")

    if schedules is not None:
        days = schedules.day(today)
        body = "\n".join(f"- {child.to_text()}" for child in days) or "Aucun emploi du temps."
        blocks.append(f"# Emploi du temps des enfants aujourd'hui\n{body}")

    if knowledge is not None:
        chunks = knowledge.search(question, top_k=top_k)
        if chunks:
            body = "\n\n".join(f"[{chunk.doc}]\n{chunk.text}" for chunk in chunks)
            blocks.append(
                "# Informations de référence (extraits des documents de la famille)\n" + body
            )

    variable = "\n\n".join(blocks)
    log.info("prompt construit : %d caractères de contexte", len(variable))
    log.debug("contexte complet :\n%s", variable)
    return INSTRUCTIONS, variable
