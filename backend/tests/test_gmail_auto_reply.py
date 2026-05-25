import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.integrations.gmail_auto_reply import _detect_language, _similarity


def test_detect_language_french() -> None:
    assert _detect_language("Bonjour, merci pour votre retour. Bien cordialement.") == "fr"


def test_detect_language_english() -> None:
    assert _detect_language("Hello, thanks for your message. Best regards.") == "en"


def test_similarity_detects_related_threads() -> None:
    first = "Demande de rendez-vous DreamLense pour un portrait professionnel"
    second = "Bonjour, merci pour votre demande DreamLense. Je suis disponible pour un rendez-vous."
    assert _similarity(first, second) > 0.2


if __name__ == "__main__":
    test_detect_language_french()
    test_detect_language_english()
    test_similarity_detects_related_threads()
    print("gmail auto reply tests OK")
