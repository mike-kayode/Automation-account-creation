from pathlib import Path

import pytest

from config.settings import Settings


def test_default_settings_are_valid():
    settings = Settings()
    assert settings.account_type == "PRO"
    assert settings.demo_deposit == 1_500_000
    assert settings.nickname == "NairaTrader 1.5M"


def test_invalid_workflow_configuration_is_rejected():
    with pytest.raises(ValueError, match="account_type must equal 'PRO'"):
        Settings(account_type="STANDARD")


def test_fixed_workflow_fields_cannot_change():
    with pytest.raises(ValueError, match="account_mode must equal 'DEMO'"):
        Settings(account_mode="LIVE")
    with pytest.raises(ValueError, match="platform must equal 'MT5'"):
        Settings(platform="MT4")
    with pytest.raises(ValueError, match="currency must equal 'NGN'"):
        Settings(currency="USD")
    with pytest.raises(ValueError, match=r"password_prefix must equal '\$Manager'"):
        Settings(password_prefix="Other")
    with pytest.raises(ValueError, match="max_password_digits must equal 5"):
        Settings(max_password_digits=4)


def test_custom_account_configuration_is_accepted():
    settings = Settings(nickname="Alpha Fund 10M", demo_deposit=10_000_000, max_leverage="1:500")
    assert settings.nickname == "Alpha Fund 10M"
    assert settings.demo_deposit == 10_000_000
    assert settings.max_leverage == "1:500"
    # Everything else keeps its fixed workflow value.
    assert settings.account_type == "PRO"
    assert settings.account_mode == "DEMO"
    assert settings.platform == "MT5"
    assert settings.currency == "NGN"
    assert settings.password_prefix == "$Manager"


@pytest.mark.parametrize(
    "leverage",
    ["1:2", "1:20", "1:50", "1:100", "1:200", "1:400", "1:500", "1:600", "1:800", "1:1000", "1:2000", "1:Unlimited"],
)
def test_any_exness_leverage_option_is_accepted(leverage: str):
    assert Settings(max_leverage=leverage).max_leverage == leverage


def test_leverage_is_normalised():
    assert Settings(max_leverage=" 1 : 500 ").max_leverage == "1:500"
    assert Settings(max_leverage="unlimited").max_leverage == "1:Unlimited"
    assert Settings(max_leverage="1:UNLIMITED").max_leverage == "1:Unlimited"


@pytest.mark.parametrize("leverage", ["", "fast", "100", "1:", "x:50", "1:50x"])
def test_invalid_leverage_is_rejected(leverage: str):
    with pytest.raises(ValueError, match="max_leverage"):
        Settings(max_leverage=leverage)


def test_blank_nickname_is_rejected():
    with pytest.raises(ValueError, match="nickname"):
        Settings(nickname="   ")


@pytest.mark.parametrize("deposit", [0, -1])
def test_non_positive_deposit_is_rejected(deposit: int):
    with pytest.raises(ValueError, match="demo_deposit"):
        Settings(demo_deposit=deposit)


def test_settings_load_from_env_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ACCOUNT_TYPE=PRO\nTEST_MODE=false\n"
        "NICKNAME=Custom Nick\nDEMO_DEPOSIT=250000\nMAX_LEVERAGE=1:500\n",
        encoding="utf-8",
    )
    settings = Settings.from_env(env_file)
    assert settings.test_mode is False
    assert settings.nickname == "Custom Nick"
    assert settings.demo_deposit == 250_000
    assert settings.max_leverage == "1:500"
