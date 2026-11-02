"""Configuration models and paths for tomato-vine."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

APP_NAME = "tomato-vine"
BASE_DIR = Path(os.environ.get("TV_HOME", Path.home() / ".config" / APP_NAME))
CONFIG_FILE = Path(os.environ.get("TV_CONFIG", BASE_DIR / "config.json"))
LOG_FILE = Path(os.environ.get("TV_LOG", BASE_DIR / "vine.log"))


class ServerConfig(BaseModel):
    """A single IRC server configuration."""

    host: str
    port: Annotated[int, Field(ge=1, le=65535)] = 6697
    tls: bool = True
    nickname: str
    username: str | None = None
    realname: str | None = None
    password: str | None = None
    sasl: SASLConfig | None = None
    nick_color: str | None = None
    channels: list[str] = Field(default_factory=list)
    auto_connect: bool = False
    ipv6: bool = False

    @field_validator("channels")
    @classmethod
    def normalize_channels(cls, v: list[str]) -> list[str]:
        return [c if c.startswith("#") else f"#{c}" for c in v]


class SASLConfig(BaseModel):
    """SASL authentication credentials."""

    mechanism: str = "PLAIN"
    username: str
    password: str


class AppConfig(BaseModel):
    """Top-level application configuration."""

    servers: list[ServerConfig] = Field(default_factory=list)
    log_level: str = "INFO"
    reconnect: bool = True
    reconnect_delay: Annotated[int, Field(ge=1, le=300)] = 5
    reconnect_max_attempts: Annotated[int, Field(ge=0, le=100)] = 10
    send_throttle_ms: Annotated[int, Field(ge=0, le=5000)] = 200
    theme: str = "dark"
    encoding: str = "utf-8"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper
