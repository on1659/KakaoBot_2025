from Lib import Helper, runtime_paths


def test_rotate_log_file_uses_real_log_name(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "SAVED_DIR", tmp_path)
    monkeypatch.setattr(Helper, "MAX_LOG_BYTES", 10)
    Helper.close_log_file()

    log_path = tmp_path / "log.log"
    log_path.write_bytes(b"x" * 11)

    Helper.rotate_log_file()

    assert not log_path.exists()
    backups = list(tmp_path.glob("log_*.log"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"x" * 11


def test_custom_print_notifies_listener(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "SAVED_DIR", tmp_path)
    Helper.close_log_file()
    seen = []
    listener = seen.append
    Helper.add_log_listener(listener)
    try:
        Helper.CustomPrint("hello-ui", saveLog=False)
    finally:
        Helper.remove_log_listener(listener)

    assert len(seen) == 1
    assert seen[0].endswith("// hello-ui")


def test_log_backups_are_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "SAVED_DIR", tmp_path)
    monkeypatch.setattr(Helper, "MAX_LOG_BYTES", 1)
    monkeypatch.setattr(Helper, "MAX_LOG_BACKUPS", 2)
    Helper.close_log_file()

    for index in range(4):
        backup = tmp_path / f"log_20260101_00000{index}.log"
        backup.write_text(str(index), encoding="utf-8")
        backup.touch()
    (tmp_path / "log.log").write_text("large", encoding="utf-8")

    Helper.rotate_log_file()

    assert len(list(tmp_path.glob("log_*.log"))) == 2
