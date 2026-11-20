import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from telethon.tl.types import Channel, ChatAdminRights, ChatPhotoEmpty

from telegram_channels_mcp import server
from telegram_channels_mcp.config import Settings
from telegram_channels_mcp.telegram import TelegramError, can_post, resolve


class FakeClient:
    async def get_entity(self, key):
        return key


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("@durov", "@durov"),
        ("durov", "durov"),
        ("https://t.me/durov/123", "durov"),
        ("t.me/s/durov", "durov"),
        ("https://t.me/c/1234567/89", -1001234567),
        ("-1001234567", -1001234567),
    ],
)
def test_resolve(ref, expected):
    assert asyncio.run(resolve(FakeClient(), ref)) == expected


def test_resolve_rejects_invites():
    with pytest.raises(TelegramError):
        asyncio.run(resolve(FakeClient(), "https://t.me/+abcdef"))


def channel(creator=False, rights=None, broadcast=True, username="mychannel"):
    return Channel(
        id=42, title="Test", photo=ChatPhotoEmpty(), date=None,
        creator=creator, admin_rights=rights, broadcast=broadcast, username=username,
    )


def test_can_post():
    assert can_post(channel(creator=True))
    assert can_post(channel(rights=ChatAdminRights(post_messages=True)))
    assert not can_post(channel())
    assert not can_post(channel(creator=True, broadcast=False))


def settings(**kw):
    base = {"api_id": 1, "api_hash": "x", "session_string": None, "session_path": None, "read_only": False}
    base.update(kw)
    return Settings(**base)


def test_check_writable(monkeypatch):
    monkeypatch.setattr(server, "_settings", settings())
    server.check_writable(channel(creator=True))
    with pytest.raises(ToolError):
        server.check_writable(channel())
    monkeypatch.setattr(server, "_settings", settings(read_only=True))
    with pytest.raises(ToolError):
        server.check_writable(channel(creator=True))
    monkeypatch.setattr(server, "_settings", settings(write_allowlist=["other"]))
    with pytest.raises(ToolError):
        server.check_writable(channel(creator=True))
    monkeypatch.setattr(server, "_settings", settings(write_allowlist=["mychannel"]))
    server.check_writable(channel(creator=True))


def test_confirm_token_binds_content():
    token = server.confirm_token_for("post", 1, "hello", None)
    assert not server.check_token(None, token)
    assert server.check_token(token, token)
    other = server.confirm_token_for("post", 1, "hello!", None)
    with pytest.raises(ToolError):
        server.check_token(other, token)


def test_check_image(tmp_path):
    pic = tmp_path / "a.png"
    pic.write_bytes(b"x")
    assert server.check_image(str(pic)).endswith("a.png")
    assert server.check_image("https://example.com/a.jpg") == "https://example.com/a.jpg"
    secret = tmp_path / "id_rsa"
    secret.write_text("key")
    for bad in (str(secret), str(tmp_path / "missing.png"), "http://example.com/a.jpg"):
        with pytest.raises(ToolError):
            server.check_image(bad)


def test_read_only_hides_write_tools(monkeypatch):
    async def names():
        return {t.name for t in await mcp.list_tools()}

    monkeypatch.setenv("TELEGRAM_READ_ONLY", "1")
    mcp = server.build_server()
    assert "publish_post" not in asyncio.run(names())
    monkeypatch.setenv("TELEGRAM_READ_ONLY", "0")
    mcp = server.build_server()
    assert {"publish_post", "reply_comment", "channel_stats"} <= asyncio.run(names())
