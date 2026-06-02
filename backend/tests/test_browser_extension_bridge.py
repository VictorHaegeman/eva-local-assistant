import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.browser_extension.bridge import (
    _safe_action_payload,
    browser_extension_status,
    is_browser_extension_ready,
    record_snapshot,
    wants_browser_extension_training,
)


SAMPLE_SNAPSHOT = {
    "tab_url": "https://example.com/training",
    "title": "Training page",
    "visible_text": "Exercice 1. Choisis la bonne reponse. Valider Suivant",
    "viewport": {"width": 1200, "height": 800},
    "elements": [
        {
            "index": 0,
            "tag": "button",
            "role": "button",
            "type": "",
            "label": "Valider",
            "text": "Valider",
            "selector": "button:nth-of-type(1)",
        },
        {
            "index": 1,
            "tag": "button",
            "role": "button",
            "type": "",
            "label": "Payer maintenant",
            "text": "Payer maintenant",
            "selector": "button:nth-of-type(2)",
        },
    ],
}


def test_browser_training_detection() -> None:
    assert wants_browser_extension_training("continue les exercices visibles dans Brave")
    assert wants_browser_extension_training("utilise l'extension brave pour cet entrainement")


def test_dangerous_browser_action_is_blocked() -> None:
    payload = _safe_action_payload(
        {"action": "click", "element_index": 1, "confidence": 0.98},
        SAMPLE_SNAPSHOT,
        "continue l'entrainement",
    )
    assert payload["action"] == "none"
    assert payload["blocked"]


def test_snapshot_makes_extension_ready() -> None:
    async def run() -> None:
        await record_snapshot(SAMPLE_SNAPSHOT)
        status = browser_extension_status()
        assert status["connected"]
        assert is_browser_extension_ready()

    asyncio.run(run())


if __name__ == "__main__":
    test_browser_training_detection()
    test_dangerous_browser_action_is_blocked()
    test_snapshot_makes_extension_ready()
    print("browser extension bridge tests OK")
