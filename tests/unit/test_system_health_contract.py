from pathlib import Path
from types import SimpleNamespace

from app.utils.system_health_checker import SystemHealthChecker, perform_startup_check


def test_startup_health_check_has_no_synchronous_network_probe():
    checker = SystemHealthChecker()

    # The startup path must not block for several DNS/TCP timeouts. Provider
    # connectivity is authoritative only when an actual translation is sent.
    assert not hasattr(checker, "check_network_connectivity")


def test_missing_speech_extra_is_a_warning_not_a_startup_failure(monkeypatch):
    real_find_spec = __import__("importlib.util").util.find_spec

    def find_spec(name):
        if name in {"whisper", "torch"}:
            return None
        return real_find_spec(name)

    monkeypatch.setattr("app.utils.system_health_checker.importlib.util.find_spec", find_spec)

    result = SystemHealthChecker().check_python_packages()

    assert result["status"] is True
    assert any("[speech]" in warning for warning in result["warnings"])
    assert not any("torch" in missing.lower() for missing in result["missing"])


def test_missing_hard_subtitle_filter_is_an_optional_warning(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(
        "subprocess.check_output", lambda *args, **kwargs: "ffmpeg version test\n"
    )
    monkeypatch.setattr(
        "app.core.video.VideoProcessor.ffmpeg_filter_names",
        classmethod(lambda cls, ffmpeg_path="ffmpeg": {"scale", "fps"}),
    )

    result = SystemHealthChecker().check_external_tools()

    assert result["status"] is True
    assert result["details"]["hard_subtitles"]["available"] is False
    assert any("libass" in warning for warning in result["warnings"])


def test_runtime_health_paths_use_user_writable_overrides(tmp_path, monkeypatch):
    config = tmp_path / "xdg config"
    cache = tmp_path / "xdg cache"
    state = tmp_path / "xdg state"
    models = tmp_path / "large volume" / "whisper models"
    monkeypatch.setenv("VIDEOTRANSLATOR_CACHE_DIR", str(cache))
    monkeypatch.setenv("VIDEOTRANSLATOR_CONFIG_DIR", str(config))
    monkeypatch.setenv("VIDEOTRANSLATOR_STATE_DIR", str(state))
    monkeypatch.setenv("VIDEOTRANSLATOR_MODEL_DIR", str(models))

    result = SystemHealthChecker().check_file_system()

    assert result["status"] is True
    assert Path(result["details"]["cache"]["path"]) == cache
    assert Path(result["details"]["models"]["path"]) == models
    assert Path(result["details"]["state"]["path"]) == state
    assert Path(result["details"]["config"]["path"]) == config
    assert all(path.is_dir() for path in (config, cache, models, state))


def test_model_check_uses_same_override_as_speech_runtime(tmp_path, monkeypatch):
    models = tmp_path / "model cache"
    models.mkdir()
    (models / "small.pt").write_bytes(b"model")
    monkeypatch.setenv("VIDEOTRANSLATOR_MODEL_DIR", str(models))

    result = SystemHealthChecker().check_model_files()

    assert Path(result["details"]["whisper_models_dir"]["path"]) == models
    assert result["details"]["available_models"] == ["small"]


def test_resource_check_targets_runtime_state_volume(tmp_path, monkeypatch):
    state = tmp_path / "redirected-volume" / "state"
    monkeypatch.setenv("VIDEOTRANSLATOR_STATE_DIR", str(state))
    observed = []
    gib = 1024**3
    monkeypatch.setattr(
        "psutil.disk_usage",
        lambda path: observed.append(path)
        or SimpleNamespace(total=20 * gib, used=5 * gib, free=15 * gib),
    )

    result = SystemHealthChecker().check_system_resources()

    assert observed == [str(state)]
    assert result["details"]["disk"]["path"] == str(state)


def test_health_report_is_saved_outside_source_tree(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setenv("VIDEOTRANSLATOR_STATE_DIR", str(state))

    report_path = Path(
        SystemHealthChecker().save_report({"system_status": "good"}, "health.json")
    )

    assert report_path == state / "logs" / "health.json"
    assert report_path.is_file()
    assert not list(report_path.parent.glob("*.tmp"))


def test_health_report_filename_cannot_escape_state_directory(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setenv("VIDEOTRANSLATOR_STATE_DIR", str(state))

    report_path = Path(
        SystemHealthChecker().save_report(
            {"system_status": "good"}, "../../unexpected.json"
        )
    )

    assert report_path == state / "logs" / "unexpected.json"


def test_startup_report_exposes_the_saved_report_path(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setenv("VIDEOTRANSLATOR_STATE_DIR", str(state))
    monkeypatch.setattr(
        SystemHealthChecker,
        "run_full_check",
        lambda self: {"system_status": "good", "warnings": []},
    )

    report = perform_startup_check()

    assert Path(report["report_path"]).parent == state / "logs"
    assert Path(report["report_path"]).is_file()
