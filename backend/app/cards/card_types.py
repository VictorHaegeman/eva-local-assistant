from dataclasses import dataclass, field
from typing import Any


@dataclass
class CardAction:
    label: str
    action_key: str
    payload: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "action_key": self.action_key, "payload": self.payload}


@dataclass
class CardItem:
    id: str
    text: str
    status: str = "pending"
    meta: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "text": self.text, "status": self.status, "meta": self.meta}


@dataclass
class Card:
    id: str
    type: str  # "task" | "calendar" | "mail" | "rdv_slot" | "priority"
    title: str
    subtitle: str = ""
    color: str = "blue"
    items: list[CardItem] = field(default_factory=list)
    actions: list[CardAction] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "subtitle": self.subtitle,
            "color": self.color,
            "items": [item.to_dict() for item in self.items],
            "actions": [action.to_dict() for action in self.actions],
        }
