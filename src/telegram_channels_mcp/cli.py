"""Command line: run the MCP server, log in once, check the session"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

from . import __version__
from .config import CONFIG_DIR, ConfigError, Settings, _load_env_files


def _ask_api_keys() -> None:
    """Asks for api_id and api_hash in the user's own terminal and stores them in the config dir"""
    _load_env_files()
    if os.environ.get("TELEGRAM_API_ID") and os.environ.get("TELEGRAM_API_HASH"):
        return
    print("api_id and api_hash are created at https://my.telegram.org/apps (API development tools)")
    api_id = input("api_id: ").strip()
    api_hash = getpass.getpass("api_hash (hidden): ").strip()
    if not api_id.isdigit() or not api_hash:
        sys.exit("api_id must be a number and api_hash must not be empty")
    os.environ["TELEGRAM_API_ID"] = api_id
    os.environ["TELEGRAM_API_HASH"] = api_hash
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    env_file = CONFIG_DIR / ".env"
    with env_file.open("a", encoding="utf-8") as f:
        f.write(f"TELEGRAM_API_ID={api_id}\nTELEGRAM_API_HASH={api_hash}\n")
    _restrict(env_file)
    print(f"Saved to {env_file}")


def _restrict(path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


async def _qr_login(client) -> None:
    """Log in by scanning a QR code in the Telegram app, no SMS or login code needed"""
    import webbrowser

    import qrcode
    import qrcode.image.svg
    from telethon import errors

    await client.connect()
    if await client.is_user_authorized():
        return
    qr_file = CONFIG_DIR / "login-qr.svg"
    qr_login = await client.qr_login()
    print()
    print("Open Telegram on your phone: Settings > Devices > Link Desktop Device, and scan the QR code")
    print(f"The QR code also opens in your browser: {qr_file}")
    print()
    try:
        while True:
            code = qrcode.QRCode(border=2)
            code.add_data(qr_login.url)
            code.print_ascii(invert=True)
            qrcode.make(qr_login.url, image_factory=qrcode.image.svg.SvgPathImage).save(str(qr_file))
            webbrowser.open(qr_file.as_uri())
            try:
                await qr_login.wait(timeout=25)
                break
            except asyncio.TimeoutError:
                print("QR code expired, here is a new one")
                print()
                await qr_login.recreate()
    except errors.SessionPasswordNeededError:
        await client.sign_in(password=getpass.getpass("2FA password (hidden): "))
    finally:
        qr_file.unlink(missing_ok=True)


async def _login(as_string: bool, use_qr: bool = False) -> None:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    from .telegram import build_client

    settings = Settings.load()
    if as_string:
        client = TelegramClient(StringSession(), settings.api_id, settings.api_hash)
    else:
        settings.session_string = None
        client = build_client(settings)
    if use_qr:
        await _qr_login(client)
    else:
        # Telethon asks for the phone number, the login code and the 2FA password right here in the terminal
        await client.start()
    me = await client.get_me()
    print(f"Logged in as {me.first_name or ''} (@{me.username or 'no username'})")
    if as_string:
        print("\nSession string. Treat it like a password: anyone with it controls your account\n")
        print(client.session.save())
    else:
        print(f"Session saved to {settings.session_path}.session")
        _restrict(f"{settings.session_path}.session")
    await client.disconnect()


async def _whoami() -> None:
    from .telegram import build_client

    settings = Settings.load()
    client = build_client(settings)
    await client.connect()
    if not await client.is_user_authorized():
        print("Not logged in. Run: telegram-channels-mcp login")
    else:
        me = await client.get_me()
        print(f"OK: {me.first_name or ''} (@{me.username or 'no username'}), read_only={settings.read_only}")
    await client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="telegram-channels-mcp",
        description="Telegram MCP server for Claude. Without a command it runs the server over stdio",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the MCP server over stdio (default)")
    login = sub.add_parser("login", help="log in to Telegram once and save the session")
    login.add_argument("--string", action="store_true", help="print a session string instead of saving a file")
    login.add_argument("--qr", action="store_true", help="log in by scanning a QR code in the Telegram app")
    sub.add_parser("whoami", help="check that the saved session works")
    args = parser.parse_args()

    try:
        if args.command == "login":
            _ask_api_keys()
            asyncio.run(_login(args.string, args.qr))
        elif args.command == "whoami":
            asyncio.run(_whoami())
        else:
            from .server import build_server

            build_server().run("stdio")
    except ConfigError as exc:
        sys.exit(str(exc))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
