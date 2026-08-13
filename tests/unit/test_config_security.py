import json
import os
import sys

from app import config as config_module


class MemoryKeyring:
    def __init__(self):
        self.values = {}

    def get_password(self, service, username):
        return self.values.get((service, username))

    def set_password(self, service, username, password):
        self.values[(service, username)] = password

    def delete_password(self, service, username):
        self.values.pop((service, username), None)


def test_config_never_serializes_api_keys(tmp_path, monkeypatch):
    keyring = MemoryKeyring()
    monkeypatch.setitem(__import__("sys").modules, "keyring", keyring)
    manager = config_module.ConfigManager(tmp_path / "config.json")

    assert manager.set_api_key("OpenAI", "secret-value")
    raw = manager.config_file.read_text(encoding="utf-8")
    assert "secret-value" not in raw
    assert "api_keys" not in json.loads(raw)
    assert manager.get_api_key("openai") == "secret-value"
    if os.name != "nt":
        assert manager.config_file.stat().st_mode & 0o777 == 0o600


def test_plaintext_legacy_key_is_migrated_out_of_json(tmp_path, monkeypatch):
    keyring = MemoryKeyring()
    monkeypatch.setitem(__import__("sys").modules, "keyring", keyring)
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"theme": "dark", "api_keys": {"deepl": "legacy-secret"}}),
        encoding="utf-8",
    )

    manager = config_module.ConfigManager(path)

    assert manager.get_api_key("deepl") == "legacy-secret"
    assert "legacy-secret" not in path.read_text(encoding="utf-8")
    assert manager.config.theme == "dark"


def test_keyring_failure_is_explicit_and_never_falls_back_to_plaintext(
    tmp_path, monkeypatch
):
    class FailingKeyring:
        def set_password(self, *args):
            raise RuntimeError("keyring locked")

        def get_password(self, *args):
            raise RuntimeError("keyring locked")

    monkeypatch.setitem(sys.modules, "keyring", FailingKeyring())
    manager = config_module.ConfigManager(tmp_path / "config.json")

    assert manager.set_api_key("OpenAI", "session-secret") is False
    assert manager.last_keyring_error == "keyring locked"
    assert manager.get_api_key("openai") == "session-secret"
    assert "session-secret" not in manager.config_file.read_text(encoding="utf-8")
    assert "api_keys" not in json.loads(manager.config_file.read_text(encoding="utf-8"))
