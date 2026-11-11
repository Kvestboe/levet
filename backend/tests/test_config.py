from pathlib import Path

import pytest

from levet.config import ConfigError, Settings


def test_only_the_password_is_required():
    settings = Settings.from_env({"LEVET_PASSWORD": "hunter2"})
    assert settings.password == "hunter2"
    assert settings.data_dir == Path("data")
    assert settings.db_path == Path("data/levet.db")
    assert settings.files_dir == Path("data/files")
    assert settings.secret_key is None
    assert settings.render_dpi == 150
    assert settings.max_upload_bytes == 50 * 1024 * 1024
    assert settings.session_days == 30


def test_everything_can_be_overridden():
    settings = Settings.from_env(
        {
            "LEVET_PASSWORD": "hunter2",
            "LEVET_DATA_DIR": "/srv/levet",
            "LEVET_SECRET_KEY": "abc",
            "LEVET_RENDER_DPI": "200",
            "LEVET_MAX_UPLOAD_MB": "10",
            "LEVET_SESSION_DAYS": "7",
        }
    )
    assert settings.db_path == Path("/srv/levet/levet.db")
    assert settings.secret_key == "abc"
    assert settings.render_dpi == 200
    assert settings.max_upload_bytes == 10 * 1024 * 1024
    assert settings.session_days == 7


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"LEVET_PASSWORD": ""},
        {"LEVET_PASSWORD": "x", "LEVET_RENDER_DPI": "high"},
        {"LEVET_PASSWORD": "x", "LEVET_RENDER_DPI": "10"},
        {"LEVET_PASSWORD": "x", "LEVET_MAX_UPLOAD_MB": "0"},
        {"LEVET_PASSWORD": "x", "LEVET_SESSION_DAYS": "-1"},
    ],
)
def test_unusable_configuration_is_rejected_with_a_config_error(env):
    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_blank_optional_values_fall_back_to_defaults():
    settings = Settings.from_env(
        {
            "LEVET_PASSWORD": "x",
            "LEVET_DATA_DIR": "",
            "LEVET_RENDER_DPI": " ",
            "LEVET_SECRET_KEY": "",
        }
    )
    assert settings.data_dir == Path("data")
    assert settings.render_dpi == 150
    assert settings.secret_key is None
