import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.memory.knowledge_ingestion import _memory_items, _title_from_path, _topic_for_title


def test_knn_document_creates_case_similarity_lessons() -> None:
    topic = _topic_for_title("K-Nearest Neighbors (KNN)")
    memories = _memory_items("KNN", topic, ["neighbors", "distance", "scaling"])
    contents = " ".join(memory.content.lower() for memory in memories)
    assert topic.key == "knn"
    assert "cas passes les plus proches" in contents
    assert "scaling" in contents


def test_metrics_document_creates_reward_lessons() -> None:
    topic = _topic_for_title("Metrics evaluation")
    memories = _memory_items("Metrics evaluation", topic, ["precision", "recall", "f1"])
    contents = " ".join(memory.content.lower() for memory in memories)
    assert topic.key == "metrics_evaluation"
    assert "rewards" in contents
    assert "precision" in contents


def test_pdf_course_titles_drive_topic_before_body_noise() -> None:
    title = _title_from_path(Path("docs/CX016-2.5-3-IML - 6 - Regression.pdf"))
    topic = _topic_for_title(title, "nearest neighbors appears elsewhere in the slides")
    assert title == "Regression"
    assert topic.key == "regression"


if __name__ == "__main__":
    test_knn_document_creates_case_similarity_lessons()
    test_metrics_document_creates_reward_lessons()
    test_pdf_course_titles_drive_topic_before_body_noise()
    print("knowledge ingestion tests OK")
