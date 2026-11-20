"""Thin layer over Telethon: one shared client, entity lookup and message formatting"""

from __future__ import annotations

import asyncio
import re
import sys
from typing import Any

from telethon import TelegramClient, utils
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, Message, User

from .config import Settings

_client: TelegramClient | None = None
_lock = asyncio.Lock()


class TelegramError(RuntimeError):
    pass


def build_client(settings: Settings) -> TelegramClient:
    if settings.session_string:
        session: Any = StringSession(settings.session_string)
    else:
        settings.session_path.parent.mkdir(parents=True, exist_ok=True)
        session = str(settings.session_path)
    return TelegramClient(
        session,
        settings.api_id,
        settings.api_hash,
        device_model="telegram-channels-mcp",
        app_version="0.1.0",
    )


async def get_client(settings: Settings) -> TelegramClient:
    """Connect lazily on the first tool call so the server starts instantly"""
    global _client
    async with _lock:
        if _client is None:
            _client = build_client(settings)
        if not _client.is_connected():
            await _client.connect()
        if not await _client.is_user_authorized():
            raise TelegramError(
                "Telegram session is not authorized. Run `telegram-channels-mcp login` "
                "in a terminal once, then restart the MCP server"
            )
        return _client


_LINK = re.compile(r"^(?:https?://)?(?:t|telegram)\.me/(?:s/)?(?P<rest>.+)$", re.I)


async def resolve(client: TelegramClient, ref: str) -> Any:
    """Accepts @username, username, t.me link, t.me/c/<id> link or numeric id"""
    ref = ref.strip()
    if not ref:
        raise TelegramError("Empty chat reference")
    key: Any = ref
    match = _LINK.match(ref)
    if match:
        rest = match.group("rest").split("?")[0].strip("/")
        parts = rest.split("/")
        if parts[0] == "c" and len(parts) > 1 and parts[1].isdigit():
            key = int(f"-100{parts[1]}")
        elif parts[0].startswith("+") or parts[0] == "joinchat":
            raise TelegramError("Invite links are not supported, join the chat first and use its name or id")
        else:
            key = parts[0]
    elif re.fullmatch(r"-?\d+", ref):
        key = int(ref)
    try:
        return await client.get_entity(key)
    except ValueError:
        # Numeric ids are only known after the dialogs were loaded once
        await client.get_dialogs(limit=None)
        try:
            return await client.get_entity(key)
        except ValueError as exc:
            raise TelegramError(f"Chat not found: {ref}") from exc


def kind_of(entity: Any) -> str:
    if isinstance(entity, User):
        return "bot" if entity.bot else "user"
    if isinstance(entity, Chat):
        return "group"
    if isinstance(entity, Channel):
        return "channel" if entity.broadcast else "group"
    return "unknown"


def is_admin(entity: Any) -> bool:
    return bool(getattr(entity, "creator", False) or getattr(entity, "admin_rights", None))


def can_post(entity: Any) -> bool:
    if not isinstance(entity, Channel) or not entity.broadcast:
        return False
    if entity.creator:
        return True
    rights = entity.admin_rights
    return bool(rights and rights.post_messages)


def post_link(entity: Any, msg_id: int) -> str | None:
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}/{msg_id}"
    if isinstance(entity, Channel):
        return f"https://t.me/c/{entity.id}/{msg_id}"
    return None


def reactions_total(msg: Message) -> int:
    if not msg.reactions or not msg.reactions.results:
        return 0
    return sum(r.count for r in msg.reactions.results)


def media_kind(msg: Message) -> str | None:
    if msg.photo:
        return "photo"
    if msg.video:
        return "video"
    if msg.gif:
        return "gif"
    if msg.voice:
        return "voice"
    if msg.audio:
        return "audio"
    if msg.sticker:
        return "sticker"
    if msg.poll:
        return "poll"
    if msg.web_preview:
        return "link_preview"
    if msg.document:
        return "file"
    return "other" if msg.media else None


def message_dict(msg: Message, entity: Any, max_chars: int = 2000) -> dict[str, Any]:
    text = msg.message or ""
    if max_chars and len(text) > max_chars:
        text = text[:max_chars] + f"… [+{len(msg.message) - max_chars} chars]"
    data: dict[str, Any] = {"id": msg.id, "date": msg.date.isoformat() if msg.date else None, "text": text}
    sender = msg.sender
    if sender is not None and not (isinstance(entity, Channel) and entity.broadcast):
        data["from"] = utils.get_display_name(sender) or getattr(sender, "username", None)
        data["from_id"] = msg.sender_id
    if msg.reply_to and msg.reply_to.reply_to_msg_id:
        data["reply_to"] = msg.reply_to.reply_to_msg_id
    kind = media_kind(msg)
    if kind:
        data["media"] = kind
    if msg.views is not None:
        data["views"] = msg.views
    if msg.forwards:
        data["forwards"] = msg.forwards
    total = reactions_total(msg)
    if total:
        data["reactions"] = total
    if msg.replies and msg.replies.replies:
        data["comments"] = msg.replies.replies
    if msg.grouped_id:
        data["album_id"] = msg.grouped_id
    link = post_link(entity, msg.id)
    if link:
        data["link"] = link
    return data


def log(text: str) -> None:
    # stdout belongs to the MCP protocol, so diagnostics go to stderr
    print(text, file=sys.stderr, flush=True)
