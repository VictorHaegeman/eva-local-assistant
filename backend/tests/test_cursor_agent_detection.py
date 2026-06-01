import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.integrations.cli_tools import find_cursor_agent, find_cursor_agent_command


def test_cursor_agent_detection_returns_command_shape() -> None:
    command = find_cursor_agent_command()
    display = find_cursor_agent()

    assert isinstance(command, list)
    assert isinstance(display, str)
    if command:
        assert display
        assert command[0]


if __name__ == "__main__":
    test_cursor_agent_detection_returns_command_shape()
    print("cursor agent detection OK")
