from pathlib import Path

from app.core.config import ROOT_ENV_FILE, Settings, get_settings


def test_settings_load_root_env_independent_of_working_directory(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert ROOT_ENV_FILE == Path(__file__).resolve().parents[2] / ".env"
    assert ROOT_ENV_FILE.name == ".env"
    assert ROOT_ENV_FILE.name != ".env.example"
    assert Settings.model_config["env_file"] == ROOT_ENV_FILE
    assert settings.database_url

    get_settings.cache_clear()
