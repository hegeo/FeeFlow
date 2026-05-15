"""WeChat platform adapter — uses pywechat for automation.

Note: This module requires the ``pywechat`` / ``pyweixin`` package
(https://github.com/Hello-Mr-Crab/pywechat) and a running WeChat client.
"""

from __future__ import annotations

import logging
from typing import Optional

from feeflow.platforms.base import Contact, PlatformAdapter

logger = logging.getLogger(__name__)


class WeChatPlatform(PlatformAdapter):
    """WeChat automation via pywechat (pywinauto-based RPA)."""

    name = "wechat"

    def __init__(self):
        self._pyweixin = None

    def _ensure_import(self):
        if self._pyweixin is not None:
            return
        try:
            import pyweixin as _pw

            self._pyweixin = _pw
        except ImportError:
            logger.warning(
                "pyweixin not installed. WeChat automation unavailable. "
                "Install with: pip install pywechat127"
            )
            self._pyweixin = False

    def send_message(self, target: str, message: str, config: dict) -> bool:
        self._ensure_import()
        if not self._pyweixin:
            logger.info("[DRY-RUN] send_message(to=%r, msg=%r)", target, message)
            return True

        try:
            from pyweixin import Messages

            Messages.send_messages_to_friend(friend=target, messages=[message])
            return True
        except Exception as e:
            logger.error("Failed to send message: %s", e)
            return False

    def quit_group(self, group_id: str, config: dict) -> bool:
        """Leave a WeChat group.

        Note: pywechat doesn't have a direct 'quit_group' API.
        This is a placeholder for when the group name is known and
        the operation can be performed through UI automation.
        """
        self._ensure_import()
        if not self._pyweixin:
            logger.info("[DRY-RUN] quit_group(group=%r)", group_id)
            return True

        logger.warning("quit_group not yet implemented via pywechat")
        return False

    def get_contacts(self, config: dict) -> list[Contact]:
        self._ensure_import()
        if not self._pyweixin:
            return []

        try:
            from pyweixin import Contacts

            friends = Contacts.get_friends()
            return [
                Contact(
                    id=f.get("wxid", ""),
                    name=f.get("remark", f.get("nickname", "")),
                    platform="wechat",
                )
                for f in friends
            ]
        except Exception as e:
            logger.error("Failed to get contacts: %s", e)
            return []

    def get_groups(self, config: dict) -> list[dict]:
        self._ensure_import()
        if not self._pyweixin:
            return []

        try:
            from pyweixin import Contacts

            return Contacts.get_chatrooms()
        except Exception as e:
            logger.error("Failed to get groups: %s", e)
            return []
