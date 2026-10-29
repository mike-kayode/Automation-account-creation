import os
import re
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Settings(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    app_name: str = "NairaTrader Demo MT5 Worker"
    exness_url: str = "https://my.exness.com/pa/trading/accounts"
    browser_profile_path: Path = Path("./browser_profile/exness")
    browser_mode: str = "attach"
    browser_cdp_endpoint: str = "http://127.0.0.1:9222"
    browser_channel: str = "chrome"
    browser_executable_path: Path | None = None
    database_path: Path = Path("./database/worker.db")
    export_directory: Path = Path("./report")
    screenshot_directory: Path = Path("./screenshots")
    # Tunable account configuration: change these in `.env` (NICKNAME,
    # DEMO_DEPOSIT, MAX_LEVERAGE) to create differently configured accounts.
    nickname: str = "NairaTrader 1.5M"
    account_mode: str = "DEMO"
    account_type: str = "PRO"
    platform: str = "MT5"
    currency: str = "NGN"
    demo_deposit: int = 1_500_000
    max_leverage: str = "1:100"
    password_prefix: str = "$Manager"
    max_password_digits: int = Field(default=5, ge=1)
    job_delay_min_seconds: int = Field(default=5, ge=0)
    job_delay_max_seconds: int = Field(default=10, ge=0)
    max_retries: int = Field(default=2, ge=0)
    session_check_interval_seconds: int = Field(default=2, ge=1)
    element_timeout_ms: int = Field(default=8_000, gt=0)
    navigation_timeout_ms: int = Field(default=20_000, gt=0)
    # Post-action settle polling (replaces blind sleeps): small interval, few tries.
    verify_poll_ms: int = Field(default=125, gt=0)
    verify_retries: int = Field(default=16, gt=0)
    encryption_key: str | None = None
    test_mode: bool = True

    @field_validator("browser_mode")
    @classmethod
    def _normalize_browser_mode(cls, value: Any) -> str:
        mode = str(value or "attach").lower()
        if mode not in {"launch", "attach"}:
            raise ValueError("browser_mode must be 'launch' or 'attach'")
        return mode

    # Fields that are part of the fixed workflow contract: they must never
    # change. The tunable account fields (nickname, demo_deposit,
    # max_leverage) are validated separately below.
    @field_validator("account_mode", "account_type", "platform", "currency", "password_prefix")
    @classmethod
    def _validate_fixed_text(cls, value: Any, info: Any) -> Any:
        expected = {
            "account_mode": "DEMO",
            "account_type": "PRO",
            "platform": "MT5",
            "currency": "NGN",
            "password_prefix": "$Manager",
        }
        field_name = info.field_name
        if field_name in expected and value != expected[field_name]:
            raise ValueError(f"{field_name} must equal {expected[field_name]!r}; got {value!r}")
        return value

    @field_validator("nickname")
    @classmethod
    def _validate_nickname(cls, value: Any) -> str:
        # Free-form: any non-empty nickname the user wants.
        nickname = str(value if value is not None else "").strip()
        if not nickname:
            raise ValueError("nickname must be a non-empty string")
        return nickname

    @field_validator("max_leverage")
    @classmethod
    def _validate_max_leverage(cls, value: Any) -> str:
        # Any leverage the Exness form offers: 1:2, 1:20, 1:50, 1:100, 1:200,
        # 1:400, 1:500, 1:600, 1:800, 1:1000, 1:2000 or 1:Unlimited.
        # Whitespace is normalised away and `unlimited` / `1:unlimited` are
        # canonicalised to the exact option text `1:Unlimited`.
        leverage = re.sub(r"\s+", "", str(value if value is not None else ""))
        if not leverage:
            raise ValueError("max_leverage must be set, e.g. '1:50', '1:100', '1:500' or '1:Unlimited'")
        if leverage.casefold() in {"unlimited", "1:unlimited"}:
            return "1:Unlimited"
        if not re.fullmatch(r"\d+:\d+", leverage):
            raise ValueError(f"max_leverage must look like '1:100' (or '1:Unlimited'); got {value!r}")
        return leverage

    @field_validator("demo_deposit")
    @classmethod
    def _validate_demo_deposit(cls, value: Any) -> int:
        # Free-form account size: any positive whole number.
        try:
            deposit = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"demo_deposit must be a positive whole number; got {value!r}") from None
        if deposit <= 0:
            raise ValueError(f"demo_deposit must be greater than 0; got {deposit}")
        return deposit

    @field_validator("max_password_digits")
    @classmethod
    def _validate_fixed_numbers(cls, value: Any, info: Any) -> Any:
        expected = {"max_password_digits": 5}
        field_name = info.field_name
        if field_name in expected and value != expected[field_name]:
            raise ValueError(f"{field_name} must equal {expected[field_name]!r}; got {value!r}")
        return value

    @classmethod
    def _check_delays(cls, min_delay: int, max_delay: int) -> None:
        if min_delay > max_delay:
            raise ValueError("job_delay_min_seconds cannot exceed job_delay_max_seconds")

    def model_post_init(self, _context: Any) -> None:
        self._check_delays(self.job_delay_min_seconds, self.job_delay_max_seconds)

    @classmethod
    def from_env(cls, env_path: str | Path = ".env") -> "Settings":
        file_values = {key.lower(): value for key, value in dotenv_values(env_path).items() if value is not None}
        values = {**file_values, **{key.lower(): value for key, value in os.environ.items()}}
        aliases = {
            "app_name": "app_name",
            "exness_url": "exness_url",
            "browser_profile_path": "browser_profile_path",
            "browser_mode": "browser_mode",
            "browser_cdp_endpoint": "browser_cdp_endpoint",
            "browser_channel": "browser_channel",
            "browser_executable_path": "browser_executable_path",
            "database_path": "database_path",
            "export_directory": "export_directory",
            "screenshot_directory": "screenshot_directory",
            "nickname": "nickname",
            "account_mode": "account_mode",
            "account_type": "account_type",
            "platform": "platform",
            "currency": "currency",
            "demo_deposit": "demo_deposit",
            "max_leverage": "max_leverage",
            "password_prefix": "password_prefix",
            "max_password_digits": "max_password_digits",
            "job_delay_min_seconds": "job_delay_min_seconds",
            "job_delay_max_seconds": "job_delay_max_seconds",
            "max_retries": "max_retries",
            "session_check_interval_seconds": "session_check_interval_seconds",
            "element_timeout_ms": "element_timeout_ms",
            "navigation_timeout_ms": "navigation_timeout_ms",
            "verify_poll_ms": "verify_poll_ms",
            "verify_retries": "verify_retries",
            "encryption_key": "encryption_key",
            "test_mode": "test_mode",
        }
        data = {aliases[key]: value for key, value in values.items() if key in aliases}
        for key in ("demo_deposit", "max_password_digits", "job_delay_min_seconds", "job_delay_max_seconds", "max_retries", "session_check_interval_seconds", "element_timeout_ms", "navigation_timeout_ms", "verify_poll_ms", "verify_retries"):
            if key in data:
                data[key] = int(data[key])
        if "test_mode" in data:
            data["test_mode"] = str(data["test_mode"]).lower() in {"1", "true", "yes", "on"}
        if data.get("browser_executable_path") == "":
            data["browser_executable_path"] = None
        instance = cls(**data)
        instance._check_delays(instance.job_delay_min_seconds, instance.job_delay_max_seconds)
        return instance
