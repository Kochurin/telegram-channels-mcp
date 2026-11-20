"""Settings come from environment variables or a .env file. Nothing secret is ever stored in the repo"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

CONFIG_DIR = Path(os.environ.get("TELEGRAM_MCP_HOME", Path.home() / ".telegram-channels-mcp"))


def _load_env_files() -> None:
    # Values already set in the environment (for example by the MCP client config) win
    load_dotenv(Path.cwd() / ".env", override=False)
    load_dotenv(CONFIG_DIR / ".env", override=False)


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [item.strip().lstrip("@").lower() for item in raw.split(",") if item.strip()]


class ConfigError(RuntimeError):
    pass


@dataclass
class Settings:
    api_id: int
    api_hash: str
    session_string: str | None
    session_path: Path
    read_only: bool
    write_allowlist: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> Settings:
        _load_env_files()
        api_id = os.environ.get("TELEGRAM_API_ID", "").strip()
        api_hash = os.environ.get("TELEGRAM_API_HASH", "").strip()
        if not api_id or not api_hash:
            raise ConfigError(
                "TELEGRAM_API_ID and TELEGRAM_API_HASH are not set. "
                "Get them at https://my.telegram.org/apps and put them into the MCP config env "
                f"or into {CONFIG_DIR / '.env'}"
            )
        if not api_id.isdigit():
            raise ConfigError("TELEGRAM_API_ID must be a number")
        session_path = Path(
            os.environ.get("TELEGRAM_SESSION_PATH", "").strip() or CONFIG_DIR / "session"
        ).expanduser()
        return cls(
            api_id=int(api_id),
            api_hash=api_hash,
            session_string=os.environ.get("TELEGRAM_SESSION_STRING", "").strip() or None,
            session_path=session_path,
            read_only=_flag("TELEGRAM_READ_ONLY"),
            write_allowlist=_list("TELEGRAM_WRITE_ALLOWLIST"),
        )
