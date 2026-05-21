"""Tests for src.config — YAML loading with env var overrides."""

import os
import textwrap

import pytest

from src.config import Settings, load_settings


class TestLoadFromYaml:
    """Load settings from a config.yaml file."""

    def test_loads_all_fields(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(textwrap.dedent("""\
            vs_token: "tok123"
            feishu_app_id: "app1"
            feishu_app_secret: "sec1"
            feishu_chat_id: "chat1"
            gemini_api_key: "gem1"
            category_id: 2
            country: "US"
            interval: "monthly"
            duration_threshold_secs: 600
            translate_top_n: 10
            feishu_folder_token: "folder1"
            feishu_domain: "example.feishu.cn"
        """))
        s = load_settings(cfg)
        assert s.vs_token == "tok123"
        assert s.category_id == 2
        assert s.country == "US"
        assert s.interval == "monthly"
        assert s.duration_threshold_secs == 600
        assert s.translate_top_n == 10
        assert s.feishu_folder_token == "folder1"
        assert s.feishu_domain == "example.feishu.cn"

    def test_defaults(self, tmp_path):
        """Optional fields use defaults when omitted."""
        cfg = tmp_path / "config.yaml"
        cfg.write_text(textwrap.dedent("""\
            vs_token: "tok"
            feishu_app_id: "a"
            feishu_app_secret: "s"
            feishu_chat_id: "c"
            gemini_api_key: "g"
        """))
        s = load_settings(cfg)
        assert s.category_id == 0
        assert s.country == "all"
        assert s.interval == "weekly"
        assert s.duration_threshold_secs == 300
        assert s.translate_top_n == 5
        assert s.feishu_folder_token is None
        assert s.feishu_domain == "skyland2020.feishu.cn"


class TestMissingRequired:
    """Required fields raise KeyError when missing."""

    def test_missing_vs_token(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("feishu_app_id: a\n")
        with pytest.raises(KeyError, match="vs_token"):
            load_settings(cfg)

    def test_missing_gemini_key(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(textwrap.dedent("""\
            vs_token: "tok"
            feishu_app_id: "a"
            feishu_app_secret: "s"
            feishu_chat_id: "c"
        """))
        with pytest.raises(KeyError, match="gemini_api_key"):
            load_settings(cfg)

    def test_empty_yaml(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("")
        with pytest.raises(KeyError):
            load_settings(cfg)

    def test_file_not_found(self, tmp_path):
        cfg = tmp_path / "nonexistent.yaml"
        with pytest.raises(KeyError):
            load_settings(cfg)


class TestEnvOverride:
    """Environment variables override YAML values."""

    def test_env_overrides_yaml(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(textwrap.dedent("""\
            vs_token: "from_yaml"
            feishu_app_id: "a"
            feishu_app_secret: "s"
            feishu_chat_id: "c"
            gemini_api_key: "g"
            country: "JP"
        """))
        monkeypatch.setenv("VS_TOKEN", "from_env")
        monkeypatch.setenv("COUNTRY", "US")
        s = load_settings(cfg)
        assert s.vs_token == "from_env"
        assert s.country == "US"

    def test_env_provides_missing_yaml(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(textwrap.dedent("""\
            feishu_app_id: "a"
            feishu_app_secret: "s"
            feishu_chat_id: "c"
            gemini_api_key: "g"
        """))
        monkeypatch.setenv("VS_TOKEN", "from_env")
        s = load_settings(cfg)
        assert s.vs_token == "from_env"


class TestSettingsFrozen:
    """Settings is immutable."""

    def test_frozen(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(textwrap.dedent("""\
            vs_token: "t"
            feishu_app_id: "a"
            feishu_app_secret: "s"
            feishu_chat_id: "c"
            gemini_api_key: "g"
        """))
        s = load_settings(cfg)
        with pytest.raises(AttributeError):
            s.vs_token = "changed"
