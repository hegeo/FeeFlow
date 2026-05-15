"""Platform adapter interface — for chat/automation platforms."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional


class Contact(dict):
    """A contact/person on a platform."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setdefault("id", "")
        self.setdefault("name", "")
        self.setdefault("platform", "")
        self.setdefault("groups", [])


class PlatformAdapter(ABC):
    """Interface for chat/automation platforms (WeChat, 企业微信, etc.)."""

    name: str = "unnamed"

    @abstractmethod
    def send_message(self, target: str, message: str, config: dict) -> bool:
        """Send a text message to a target (contact or group)."""

    @abstractmethod
    def quit_group(self, group_id: str, config: dict) -> bool:
        """Leave a group chat."""

    def get_contacts(self, config: dict) -> list[Contact]:
        """Retrieve contacts from the platform."""
        return []

    def get_groups(self, config: dict) -> list[dict]:
        """Retrieve group list from the platform."""
        return []

    def on_event(self, event_type: str, callback: Callable, config: dict) -> None:
        """Subscribe to platform events (new message, new member, etc.)."""
        pass

    def validate_config(self, config: dict) -> list[str]:
        return []
