"""Board of Directors d'Eva: CEO / CTO / CFO comme cerveau d'opérateur.

Chaque demande de réflexion passe par des agents distincts (appels LLM séparés),
chacun avec un rôle précis et sa propre tranche de mémoire Obsidian (salle du conseil
`01 - Board/`). Le board ne remplace pas les outils locaux: il décide en amont de la
réponse finale et fournit une délibération + une trace.
"""

from app.board.boardroom import BoardDeliberation, run_board_deliberation

__all__ = ["BoardDeliberation", "run_board_deliberation"]
