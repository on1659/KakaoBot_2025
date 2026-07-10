# -*- coding: utf-8 -*-
import sys
from pathlib import Path

import pytest

# 저장소 루트를 import 경로에 추가 (Lib 패키지)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _isolate_instagram_error_log(tmp_path, monkeypatch):
    """테스트의 log_error 호출이 실제 saved/instagram_errors.log를 오염시키지 않게 격리."""
    from Lib import insta
    monkeypatch.setattr(insta, "ERROR_LOG_FILE", tmp_path / "instagram_errors.log")
