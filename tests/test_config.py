import importlib.util

import pytest

from coding_best_practices_for_oss import config


@pytest.fixture
def ai_configured(monkeypatch):
    monkeypatch.setattr(config, "AI_MODEL_ENABLED", "true")
    monkeypatch.setattr(config, "AI_MODEL_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr(config, "AI_MODEL_API_KEY", "key")
    monkeypatch.setattr(config, "AI_MODEL_NAME", "model")


@pytest.fixture
def ai_not_configured(monkeypatch):
    monkeypatch.setattr(config, "AI_MODEL_ENABLED", "true")
    monkeypatch.setattr(config, "AI_MODEL_NAME", "")


def write(tmp_path, content):
    path = tmp_path / "config.yaml"
    path.write_text(content)
    return path


class TestLoadConfig:
    @pytest.mark.parametrize(
        "content",
        ["rules:\n  DOC001:\n    severity: MAJOR\n", "rules: {}\ndependencies:\n", ""],
        ids=["no-dependencies-section", "empty-dependencies-section", "empty-file"],
    )
    def test_the_dependencies_section_is_optional(self, tmp_path, ai_not_configured, content):
        loaded = config.load_config(write(tmp_path, content))
        assert loaded["dependencies"]["ai"] == {"enabled": False}

    def test_missing_ai_settings_disable_ai_without_a_config_file(self, monkeypatch, ai_not_configured):
        monkeypatch.setattr(config, "CONFIG_FILE", "")
        assert config.load_config()["dependencies"]["ai"] == {"enabled": False}

    def test_ai_can_be_turned_off_without_a_config_file(self, monkeypatch, ai_configured):
        monkeypatch.setattr(config, "CONFIG_FILE", "")
        monkeypatch.setattr(config, "AI_MODEL_ENABLED", "false")
        assert config.load_config()["dependencies"]["ai"] == {"enabled": False}

    def test_configured_ai_is_left_enabled(self, tmp_path, ai_configured):
        loaded = config.load_config(write(tmp_path, "rules: {}\n"))
        assert "ai" not in loaded["dependencies"]

    def test_the_other_settings_are_kept(self, tmp_path, ai_not_configured):
        loaded = config.load_config(
            write(tmp_path, "rules:\n  DOC001:\n    severity: MAJOR\ndependencies:\n  flake8:\n    enabled: false\n")
        )
        assert loaded["rules"] == {"DOC001": {"severity": "MAJOR"}}
        assert loaded["dependencies"]["flake8"] == {"enabled": False}

    def test_ruff_is_disabled_when_not_installed(self, monkeypatch, ai_configured):
        monkeypatch.setattr(config, "CONFIG_FILE", "")
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
        assert config.load_config()["dependencies"]["ruff"] == {"enabled": False}
