# -*- coding: utf-8 -*-
"""Lib/insta.py 단위 테스트 (docs/instagram_기능_복구_작업계획.md §7)"""
import time
from io import BytesIO
from types import SimpleNamespace

import pytest
import instaloader
from PIL import Image

from Lib import insta


@pytest.fixture(autouse=True)
def reset_loader_state():
    """모듈 싱글턴 상태를 테스트마다 초기화."""
    insta._loader = None
    insta._last_reload_attempt = 0.0
    yield
    insta._loader = None
    insta._last_reload_attempt = 0.0


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(insta.time, "sleep", lambda s: None)


# ─── shortcode 추출 (§4.4) ───────────────────────────────────────────
# 입력은 디스패처가 실제로 넘기는 형태: chat_command + split_command(message) 재접합

@pytest.mark.parametrize("text,expected", [
    # 순수 URL 한 줄 (가장 흔한 입력 — 재접합하면 원본 URL 복원)
    ("https://www.instagram.com/p/DIpzzT_TBor/", "DIpzzT_TBor"),
    ("https://www.instagram.com/reel/ABC-12_3/", "ABC-12_3"),
    ("https://www.instagram.com/reels/XyZ99/", "XyZ99"),
    # www 없는 URL
    ("https://instagram.com/p/SHORTcode1/", "SHORTcode1"),
    # 쿼리 문자열
    ("https://www.instagram.com/p/DIpzzT_TBor/?igsh=MWVs&img_index=2", "DIpzzT_TBor"),
    # 문장 중간 URL (디스패처 재접합으로 훼손된 형태 포함)
    ("https://www.instagram.com/봐봐 https://www.instagram.com/p/QQQ111/ 웃김", "QQQ111"),
    # 둘째 줄 URL (parse가 \n으로 이어붙인 메시지)
    ("https://www.instagram.com/첫줄\nhttps://www.instagram.com/reel/LINE2code/", "LINE2code"),
])
def test_extract_shortcode_supported(text, expected):
    assert insta.extract_shortcode(text) == expected


@pytest.mark.parametrize("text", [
    "https://www.instagram.com/username",            # 프로필
    "https://www.instagram.com/stories/user/123/",   # 스토리
    "https://www.instagram.com/share/p/AbCdEf/",     # 공유 리디렉션
    "https://www.instagram.com/",                    # 루트
    "그냥 텍스트",
    "",
])
def test_extract_shortcode_unsupported(text):
    assert insta.extract_shortcode(text) is None


def test_extract_shortcode_none_input():
    assert insta.extract_shortcode(None) is None


# ─── 오류 분류 (§4.6) ───────────────────────────────────────────────

def _run_fetch(monkeypatch, raiser):
    calls = {"n": 0}

    def fake_from_shortcode(context, shortcode):
        calls["n"] += 1
        result = raiser(calls["n"])
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(instaloader.Post, "from_shortcode", staticmethod(fake_from_shortcode))
    loader = SimpleNamespace(context=None)
    url, err = insta._fetch_thumbnail_url(loader, "TESTCODE")
    return url, err, calls["n"]


def test_permanent_not_found_no_retry(monkeypatch, no_sleep):
    exc = instaloader.exceptions.QueryReturnedNotFoundException("404")
    url, err, n = _run_fetch(monkeypatch, lambda i: exc)
    assert url is None and err == insta.MSG_GONE and n == 1


def test_permanent_private_no_retry(monkeypatch, no_sleep):
    exc = instaloader.exceptions.PrivateProfileNotFollowedException("private")
    url, err, n = _run_fetch(monkeypatch, lambda i: exc)
    assert url is None and err == insta.MSG_GONE and n == 1


def test_bad_response_no_retry(monkeypatch, no_sleep):
    exc = instaloader.exceptions.BadResponseException("Fetching Post metadata failed.")
    url, err, n = _run_fetch(monkeypatch, lambda i: exc)
    assert url is None and err == insta.MSG_BAD_RESPONSE and n == 1


def test_login_required_invalidates_loader(monkeypatch, no_sleep):
    insta._loader = SimpleNamespace()  # 세션 로더가 있는 상태에서
    exc = instaloader.exceptions.LoginRequiredException("login required")
    url, err, n = _run_fetch(monkeypatch, lambda i: exc)
    assert url is None and err == insta.MSG_SESSION and n == 1
    assert insta._loader is None  # 싱글턴 무효화 (§4.2-5)


def test_abort_download_invalidates_loader(monkeypatch, no_sleep):
    # 세션 만료의 실제 경로: 세션 파일 로드 후에는 is_logged_in이 항상 참이라
    # 라이브러리가 LoginRequired 대신 AbortDownload(일반 Exception 하위)를 던진다.
    # 안 잡으면 방 무응답 + 로더 미무효화로 재시작 전까지 침묵 반복.
    insta._loader = SimpleNamespace()
    exc = instaloader.exceptions.AbortDownloadException("Redirected to login page.")
    url, err, n = _run_fetch(monkeypatch, lambda i: exc)
    assert url is None and err == insta.MSG_SESSION and n == 1
    assert insta._loader is None


def test_rate_limit_detected_from_connection_exception(monkeypatch, no_sleep):
    # 429는 TooManyRequestsException으로 오지 않는다 — ConnectionException 메시지로 판별 (§4.6)
    exc = instaloader.exceptions.ConnectionException(
        "JSON Query to graphql/query: 429 Too Many Requests")
    url, err, n = _run_fetch(monkeypatch, lambda i: exc)
    assert url is None and err == insta.MSG_RATE_LIMITED and n == 1


def test_transient_retries_exactly_once(monkeypatch, no_sleep):
    exc = instaloader.exceptions.ConnectionException("read timed out")
    url, err, n = _run_fetch(monkeypatch, lambda i: exc)
    assert url is None and err == insta.MSG_TRANSIENT and n == 2  # 최초 1회 + 재시도 1회


def test_transient_then_success(monkeypatch, no_sleep):
    exc = instaloader.exceptions.ConnectionException("connection reset")
    post = SimpleNamespace(url="https://cdn.example/img.jpg")
    url, err, n = _run_fetch(monkeypatch, lambda i: exc if i == 1 else post)
    assert url == "https://cdn.example/img.jpg" and err is None and n == 2


# ─── GetData 계약 (§4.5) ─────────────────────────────────────────────

def test_getdata_unsupported_url_no_network(monkeypatch):
    called = {"embed": False, "loader": False}
    monkeypatch.setattr(insta, "_fetch_thumbnail_url_embed", lambda s: called.update(embed=True))
    monkeypatch.setattr(insta, "get_loader", lambda: called.update(loader=True))
    result, rtype = insta.GetData("방", "https://www.instagram.com/", "username")
    assert rtype == "text" and result == insta.MSG_UNSUPPORTED
    assert not called["embed"] and not called["loader"]  # 추출 실패 시 네트워크 접근 없음


def test_getdata_embed_success_never_touches_session(monkeypatch):
    # 비로그인 embed가 기본 경로 — 세션이 없어도 동작해야 한다
    monkeypatch.setattr(insta, "_fetch_thumbnail_url_embed", lambda s: ("https://cdn/x.jpg", None))
    monkeypatch.setattr(insta, "get_loader", lambda: pytest.fail("세션을 건드리면 안 됨"))
    monkeypatch.setattr(insta.requests, "get", lambda url, headers=None, timeout=None: _fake_jpeg_response())
    payload, rtype = insta.GetData("방", "https://www.instagram.com/", "p/ABC123/")
    assert rtype == "image" and isinstance(payload, bytes)


def test_getdata_embed_miss_without_session_returns_gone(monkeypatch):
    monkeypatch.setattr(insta, "_fetch_thumbnail_url_embed", lambda s: (None, None))
    monkeypatch.setattr(insta, "get_loader", lambda: None)
    result, rtype = insta.GetData("방", "https://www.instagram.com/", "p/ABC123/")
    assert (result, rtype) == (insta.MSG_GONE, "text")


def test_getdata_embed_miss_falls_back_to_session(monkeypatch):
    monkeypatch.setattr(insta, "_fetch_thumbnail_url_embed", lambda s: (None, None))
    monkeypatch.setattr(insta, "get_loader", lambda: SimpleNamespace(context=None))
    monkeypatch.setattr(insta, "_fetch_thumbnail_url", lambda l, s: ("https://cdn/private.jpg", None))
    monkeypatch.setattr(insta.requests, "get", lambda url, headers=None, timeout=None: _fake_jpeg_response())
    payload, rtype = insta.GetData("방", "https://www.instagram.com/", "p/ABC123/")
    assert rtype == "image" and isinstance(payload, bytes)


def test_getdata_embed_rate_limited_short_circuits(monkeypatch):
    # embed가 429를 주면 세션 폴백으로 요청을 더 보내지 않는다
    monkeypatch.setattr(insta, "_fetch_thumbnail_url_embed", lambda s: (None, insta.MSG_RATE_LIMITED))
    monkeypatch.setattr(insta, "get_loader", lambda: pytest.fail("429에 폴백하면 안 됨"))
    result, rtype = insta.GetData("방", "https://www.instagram.com/", "p/ABC123/")
    assert (result, rtype) == (insta.MSG_RATE_LIMITED, "text")


def test_getdata_fetch_error_returns_text(monkeypatch):
    monkeypatch.setattr(insta, "_fetch_thumbnail_url_embed", lambda s: (None, None))
    monkeypatch.setattr(insta, "get_loader", lambda: SimpleNamespace(context=None))
    monkeypatch.setattr(insta, "_fetch_thumbnail_url", lambda l, s: (None, insta.MSG_GONE))
    result, rtype = insta.GetData("방", "https://www.instagram.com/", "p/ABC123/")
    assert (result, rtype) == (insta.MSG_GONE, "text")


# ─── 비로그인 embed 경로 ─────────────────────────────────────────────

def _embed_html(img_url):
    return f'<html><img class="EmbeddedMediaImage" src="{img_url}" /></html>'


def test_embed_extracts_and_unescapes_url(monkeypatch):
    escaped = "https://scontent.cdninstagram.com/v/t51.jpg?a=1&amp;b=2"
    monkeypatch.setattr(insta.requests, "get", lambda url, headers=None, timeout=None:
                        SimpleNamespace(status_code=200, text=_embed_html(escaped)))
    url, err = insta._fetch_thumbnail_url_embed("ABC123")
    assert err is None
    assert url == "https://scontent.cdninstagram.com/v/t51.jpg?a=1&b=2"  # HTML 엔티티 복원


def test_embed_uses_facebook_user_agent(monkeypatch):
    # 브라우저 UA면 로그인 월이 뜬다 — UA가 결정적이다
    seen = {}

    def spy(url, headers=None, timeout=None):
        seen["ua"] = (headers or {}).get("User-Agent", "")
        seen["url"] = url
        return SimpleNamespace(status_code=200, text=_embed_html("https://cdn/x.jpg"))

    monkeypatch.setattr(insta.requests, "get", spy)
    insta._fetch_thumbnail_url_embed("ABC123")
    assert "facebookexternalhit" in seen["ua"]
    assert seen["url"].endswith("/p/ABC123/embed/captioned/")


def test_embed_429_returns_rate_limit_message(monkeypatch):
    monkeypatch.setattr(insta.requests, "get", lambda url, headers=None, timeout=None:
                        SimpleNamespace(status_code=429, text=""))
    url, err = insta._fetch_thumbnail_url_embed("ABC123")
    assert url is None and err == insta.MSG_RATE_LIMITED


def test_embed_no_media_signals_fallback(monkeypatch):
    # 미디어 태그 없음 → (None, None) = "세션 폴백을 시도하라"
    monkeypatch.setattr(insta.requests, "get", lambda url, headers=None, timeout=None:
                        SimpleNamespace(status_code=200, text="<html>Sorry</html>"))
    assert insta._fetch_thumbnail_url_embed("ABC123") == (None, None)


def test_embed_network_error_signals_fallback(monkeypatch):
    def boom(url, headers=None, timeout=None):
        raise insta.requests.Timeout("timed out")
    monkeypatch.setattr(insta.requests, "get", boom)
    assert insta._fetch_thumbnail_url_embed("ABC123") == (None, None)


def _fake_jpeg_response():
    buf = BytesIO()
    Image.new("RGB", (2, 2), (255, 0, 0)).save(buf, "JPEG")
    return SimpleNamespace(status_code=200, content=buf.getvalue(),
                           headers={"Content-Type": "image/jpeg"})


def test_getdata_success_returns_dib_bytes(monkeypatch):
    monkeypatch.setattr(insta, "_fetch_thumbnail_url_embed", lambda s: ("https://cdn/x.jpg", None))
    monkeypatch.setattr(insta.requests, "get", lambda url, headers=None, timeout=None: _fake_jpeg_response())
    payload, rtype = insta.GetData("방", "https://www.instagram.com/", "p/ABC123/")
    assert rtype == "image"
    assert isinstance(payload, bytes)
    assert not payload.startswith(b"BM")          # BMP 파일 헤더가 제거된 DIB여야 함
    assert payload[:4] == b"\x28\x00\x00\x00"     # BITMAPINFOHEADER 크기(40)로 시작


def test_getdata_download_failure_returns_text_not_image(monkeypatch):
    # 회귀: 다운로드 실패가 ("", "image")로 새어나가 채팅 로그를 붙여넣던 버그 (§4.5)
    monkeypatch.setattr(insta, "_fetch_thumbnail_url_embed", lambda s: ("https://cdn/x.jpg", None))
    monkeypatch.setattr(insta.requests, "get", lambda url, headers=None, timeout=None:
                        SimpleNamespace(status_code=404, content=b"", headers={}))
    result, rtype = insta.GetData("방", "https://www.instagram.com/", "p/ABC123/")
    assert rtype == "text" and result == insta.MSG_IMAGE_FAIL


# ─── 세션 로더 (§4.2) ───────────────────────────────────────────────

def test_get_loader_without_username(monkeypatch):
    monkeypatch.delenv("IG_USERNAME", raising=False)
    assert insta.get_loader() is None


def test_get_loader_reload_throttle(monkeypatch):
    monkeypatch.setenv("IG_USERNAME", "testuser")
    # 직전에 시도가 있었던 상태 → 10분 내 재시도는 즉시 None
    insta._last_reload_attempt = time.monotonic()
    assert insta.get_loader() is None
    # 스로틀 해제 후에는 다시 시도한다 (세션 파일이 없으므로 결과는 None이지만 시도는 함)
    insta._last_reload_attempt = 0.0
    monkeypatch.setattr(insta, "SESSION_DIR", insta.SESSION_DIR / "no_such_dir")
    assert insta.get_loader() is None
    assert insta._last_reload_attempt > 0  # 시도가 기록됨


def _fake_loader_factory(test_login_result):
    class FakeLoader:
        def __init__(self, **kwargs):
            pass

        def load_session_from_file(self, username, filename):
            pass

        def test_login(self):
            if isinstance(test_login_result, Exception):
                raise test_login_result
            return test_login_result
    return FakeLoader


def _prepare_session_env(monkeypatch, tmp_path, username="testuser"):
    monkeypatch.setenv("IG_USERNAME", username)
    session_dir = tmp_path / "instagram"
    session_dir.mkdir()
    (session_dir / f"session-{username}").write_bytes(b"fake")
    monkeypatch.setattr(insta, "SESSION_DIR", session_dir)


def test_get_loader_unverified_session_is_used(monkeypatch, tmp_path):
    # test_login=None은 만료·순단·429·구 엔드포인트 폐기를 구분 못 한다 —
    # 거부하면 유효한 세션도 영구 차단되므로 미검증 상태로 통과해야 한다 (§4.6)
    _prepare_session_env(monkeypatch, tmp_path)
    monkeypatch.setattr(insta.instaloader, "Instaloader", _fake_loader_factory(None))
    assert insta.get_loader() is not None


def test_get_loader_wrong_account_rejected(monkeypatch, tmp_path):
    _prepare_session_env(monkeypatch, tmp_path)
    monkeypatch.setattr(insta.instaloader, "Instaloader", _fake_loader_factory("someone_else"))
    assert insta.get_loader() is None


def test_get_loader_verified_session_cached(monkeypatch, tmp_path):
    _prepare_session_env(monkeypatch, tmp_path)
    monkeypatch.setattr(insta.instaloader, "Instaloader", _fake_loader_factory("testuser"))
    loader = insta.get_loader()
    assert loader is not None
    assert insta.get_loader() is loader  # 싱글턴 재사용


def test_get_loader_username_case_insensitive(monkeypatch, tmp_path):
    # 회귀: 운영자가 config에 대문자로 적으면 유효한 세션이 영구 거부되던 버그
    _prepare_session_env(monkeypatch, tmp_path, username="MyBotAccount")
    monkeypatch.setattr(insta.instaloader, "Instaloader", _fake_loader_factory("mybotaccount"))
    assert insta.get_loader() is not None


def test_get_loader_test_login_raises_treated_as_unverified(monkeypatch, tmp_path):
    # 회귀: test_login이 400/KeyError로 크래시하면 방이 무응답이 되던 버그
    _prepare_session_env(monkeypatch, tmp_path)
    exc = instaloader.exceptions.QueryReturnedBadRequestException("400")
    monkeypatch.setattr(insta.instaloader, "Instaloader", _fake_loader_factory(exc))
    assert insta.get_loader() is not None  # 미검증으로 통과


def test_getdata_never_raises(monkeypatch):
    # 회귀: 핸들러에서 예외가 새면 디스패처 광역 except가 삼켜 방이 무응답이 된다
    def boom(s):
        raise RuntimeError("unexpected")
    monkeypatch.setattr(insta, "_fetch_thumbnail_url_embed", boom)
    result, rtype = insta.GetData("방", "https://www.instagram.com/", "p/ABC123/")
    assert rtype == "text" and result == insta.MSG_BAD_RESPONSE


def test_no_password_login_anywhere():
    """비밀번호 로그인 경로가 코드에서 제거됐는지 (§4.2)."""
    import inspect
    src = inspect.getsource(insta)
    assert ".login(" not in src
    assert "IG_PASSWORD" not in src
