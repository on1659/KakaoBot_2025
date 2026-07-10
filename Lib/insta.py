# -*- coding: utf-8 -*-
"""
Instagram 게시물/릴스 대표 이미지 조회 (docs/instagram_기능_복구_작업계획.md v2)

- 1차 경로: 비로그인 oEmbed 스크래핑. /p/<code>/embed/captioned/ 를 facebookexternalhit
  User-Agent로 요청하면 로그인 월 없이 EmbeddedMediaImage(대표 이미지)가 내려온다.
  계정도 세션도 필요 없고 차단 위험이 없어 기본 경로로 쓴다.
  (일반 브라우저 UA로는 로그인 월이 뜬다 — UA가 결정적이다.)
- 2차 경로(선택): 세션 파일이 있으면 instaloader로 재시도. embed가 막는 비공개
  게시물 등을 커버한다. 세션이 없으면 그냥 건너뛴다 — 필수 아님.
- 반환 계약: 성공 시 (DIB 바이트, "image") — BMP 인코딩 후 14바이트 파일 헤더 제거.
  실패 시 (원인별 안내문, "text"). 클립보드 조작은 전송자(chat_process)가 소유한다. (§4.5)
- 오류 분류가 재시도보다 먼저다 (§4.6). 일시 오류만 1회 재시도.
"""
import html as htmllib
import os
import re
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

import requests
import instaloader
from PIL import Image
from Lib import Helper

try:
    import pillow_heif
    pillow_heif.register_heif_opener()  # 설치만으로는 Image.open에 연결되지 않는다 (§4.5)
except ImportError:
    pass

REPO_ROOT = Path(__file__).resolve().parents[1]
SESSION_DIR = REPO_ROOT / "saved" / "instagram"
ERROR_LOG_FILE = REPO_ROOT / "saved" / "instagram_errors.log"

# 게시물/릴스 URL에서 shortcode 추출. 프로필/스토리/공유 리디렉션은 매치되지 않는다 (§4.4)
URL_PATTERN = re.compile(r"https://(?:www\.)?instagram\.com/(?:p|reel|reels)/([A-Za-z0-9_-]+)")

# embed 페이지의 대표 이미지. 이 UA여야 로그인 월이 뜨지 않는다.
EMBED_IMG_PATTERN = re.compile(r'class="EmbeddedMediaImage"[^>]*?src="([^"]+)"')
EMBED_UA = {"User-Agent": "Mozilla/5.0 (compatible; facebookexternalhit/1.1)"}

RELOAD_INTERVAL_SEC = 600  # 세션 재로드 시도 간격 (§4.2-5)
EMBED_TIMEOUT_SEC = 8      # embed 페이지 요청 타임아웃
IMAGE_TIMEOUT_SEC = 5      # 이미지 다운로드 타임아웃 (§4.5)

ERROR_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

MSG_UNSUPPORTED = "인스타그램 게시물/릴스 링크만 지원합니다."
MSG_SESSION = "인스타그램 세션 확인이 필요합니다. 관리자에게 문의해주세요."
MSG_GONE = "이 게시물은 삭제됐거나 접근할 수 없습니다."
MSG_BAD_RESPONSE = "게시물을 가져오지 못했습니다."
MSG_RATE_LIMITED = "인스타그램 요청 제한에 걸렸습니다. 잠시 후 다시 시도해주세요."
MSG_TRANSIENT = "일시적인 오류로 이미지를 가져오지 못했습니다."
MSG_IMAGE_FAIL = "이미지 다운로드에 실패했습니다."

# 세션 로더 싱글턴 (§4.2). 실패는 캐시하지 않고, 재로드는 RELOAD_INTERVAL로 스로틀.
_loader = None
_last_reload_attempt = 0.0


def log_error(error_msg):
    """오류를 saved/instagram_errors.log에 기록한다 (§4.6)."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {error_msg}\n")
    except OSError:
        pass
    Helper.CustomPrint(f"❌ [insta] {error_msg}")


def extract_shortcode(text):
    """문자열 어디에 있든 게시물/릴스 shortcode를 찾는다. 없으면 None (§4.4)."""
    match = URL_PATTERN.search(text or "")
    return match.group(1) if match else None


def _invalidate_loader():
    global _loader
    _loader = None


def get_loader():
    """
    세션 파일 기반 로더를 반환한다. 유효한 로더가 없으면 None (§4.2).
    - test_login()은 로더 생성 시 1회만 호출한다.
    - 로더 없음 상태의 재로드 시도는 RELOAD_INTERVAL_SEC당 1회로 제한한다.
    """
    global _loader, _last_reload_attempt
    if _loader is not None:
        return _loader

    now = time.monotonic()
    if _last_reload_attempt and now - _last_reload_attempt < RELOAD_INTERVAL_SEC:
        return None
    _last_reload_attempt = now

    # IG_USERNAME은 config/api_key.json → load_api_keys()가 os.environ에 주입한 값 (§4.2)
    username = os.environ.get("IG_USERNAME", "").strip()
    if not username:
        log_error("IG_USERNAME 없음 — config/api_key.json 확인")
        return None

    session_file = SESSION_DIR / f"session-{username}"
    if not session_file.exists():
        log_error(f"세션 파일 없음: {session_file} — tools/create_instagram_session.py로 생성 필요")
        return None

    # sleep=False: 기본값은 매 요청 전 최대 15초 랜덤 슬립 (§4.2)
    # max_connection_attempts=1: 내부 재시도를 꺼서 §4.6 분류가 유일한 재시도 층이 되게 함
    loader = instaloader.Instaloader(
        sleep=False, request_timeout=10, max_connection_attempts=1,
        download_pictures=False, quiet=True,
    )
    try:
        loader.load_session_from_file(username, str(session_file))
    except Exception as e:
        log_error(f"세션 로드 실패: {e}")
        return None

    # test_login은 구 GraphQL 해시를 쓰므로(4.15.2 동일) None 반환 외에
    # QueryReturnedBadRequestException(400)이나 KeyError(응답 구조 변경)를 던질 수도 있다
    try:
        who = loader.test_login()
    except Exception as e:
        log_error(f"세션 검증 요청 실패 ({type(e).__name__}: {e}) — 미검증으로 진행")
        who = None

    # 사용자명 비교는 대소문자 무시 — Instagram은 소문자 정규형을 반환하므로
    # 운영자가 config에 대문자로 적으면 유효한 세션이 영구 거부된다
    if who is not None and who.casefold() != username.casefold():
        log_error(f"세션 계정 불일치 (test_login={who!r}, 기대={username}) — 세션 도구로 재생성 필요")
        return None
    if who is None:
        # None은 만료·네트워크 순단·429·엔드포인트 폐기를 구분하지 못한다.
        # 여기서 거부하면 유효한 세션도 영구 차단되므로 미검증 상태로 통과시킨다 —
        # 진짜 무효라면 첫 조회의 세션 오류(AbortDownload/LoginRequired)가
        # 로더를 무효화하고 세션 안내를 보낸다 (§4.6).
        Helper.CustomPrint("⚠️ Instagram 세션 검증 미확정 (test_login=None) — 미검증 상태로 사용")
    else:
        Helper.CustomPrint("✅ Instagram 세션 로드 완료")

    _loader = loader
    return _loader


def _fetch_thumbnail_url_embed(shortcode):
    """
    비로그인 embed 스크래핑. 반환: (url, None) / (None, 안내문) / (None, None).
    (None, None)은 "여기선 못 찾았으니 세션 폴백을 시도해봐라"는 뜻이다.
    """
    url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    try:
        resp = requests.get(url, headers=EMBED_UA, timeout=EMBED_TIMEOUT_SEC)
    except requests.RequestException as e:
        log_error(f"embed 요청 실패 ({shortcode}): {e}")
        return None, None

    if resp.status_code == 429:
        log_error(f"embed 요청 제한 ({shortcode})")
        return None, MSG_RATE_LIMITED
    if resp.status_code != 200:
        log_error(f"embed 응답 이상 ({shortcode}, status={resp.status_code})")
        return None, None

    match = EMBED_IMG_PATTERN.search(resp.text)
    if not match:
        # 삭제·비공개·미디어 없음. 세션이 있으면 폴백이 더 정확히 판정한다.
        return None, None
    return htmllib.unescape(match.group(1)), None


def _fetch_thumbnail_url(loader, shortcode):
    """
    게시물 대표 이미지 URL을 가져온다. 반환: (url, None) 또는 (None, 안내문).
    예외 분류는 §4.6 표. 하위 클래스를 상위보다 먼저 잡아야 한다:
    QueryReturnedNotFound/TooManyRequests는 ConnectionException의 하위다.
    """
    attempts = 0
    while True:
        try:
            post = instaloader.Post.from_shortcode(loader.context, shortcode)
            return post.url, None
        except (instaloader.exceptions.QueryReturnedNotFoundException,
                instaloader.exceptions.PrivateProfileNotFollowedException):
            return None, MSG_GONE
        except (instaloader.exceptions.LoginRequiredException,
                instaloader.exceptions.AbortDownloadException) as e:
            # 세션 만료의 실제 경로는 AbortDownloadException이다: 세션 파일 로드 후에는
            # is_logged_in이 항상 참이라, 로그인 페이지 리디렉션/체크포인트 요구 시
            # 라이브러리가 LoginRequired 대신 AbortDownload(일반 Exception 하위,
            # InstaloaderException 아님)를 던진다. 안 잡으면 무응답 + 로더 미무효화.
            log_error(f"세션 인증 거부 ({type(e).__name__}): {e}")
            _invalidate_loader()
            return None, MSG_SESSION
        except instaloader.exceptions.BadResponseException as e:
            # 삭제/차단 외에 응답 구조 변경으로도 발생 — 원본을 남겨 라이브러리 업데이트 판단 근거로
            log_error(f"BadResponse ({shortcode}): {e}")
            return None, MSG_BAD_RESPONSE
        except instaloader.exceptions.ConnectionException as e:
            # 429는 TooManyRequestsException으로 오지 않는다 — 라이브러리가 내부에서 잡아
            # 평범한 ConnectionException으로 재포장한다 (§4.6)
            if "429" in str(e) or "Too Many Requests" in str(e) or isinstance(
                    e.__cause__, instaloader.exceptions.TooManyRequestsException):
                log_error(f"요청 제한 ({shortcode}): {e}")
                return None, MSG_RATE_LIMITED
            attempts += 1
            if attempts > 1:
                log_error(f"일시 오류 재시도 실패 ({shortcode}): {e}")
                return None, MSG_TRANSIENT
            time.sleep(1)
        except instaloader.exceptions.InstaloaderException as e:
            log_error(f"미분류 오류 ({shortcode}): {e}")
            return None, MSG_BAD_RESPONSE


def _download_dib(image_url):
    """
    이미지를 받아 CF_DIB용 DIB 바이트로 변환한다. 반환: (dib_bytes, None) 또는 (None, 안내문).
    DIB = BMP 인코딩에서 앞 14바이트 BITMAPFILEHEADER 제거 (§4.5).
    """
    try:
        resp = requests.get(image_url, headers=EMBED_UA, timeout=IMAGE_TIMEOUT_SEC)
        if resp.status_code != 200:
            log_error(f"이미지 다운로드 실패 (status={resp.status_code})")
            return None, MSG_IMAGE_FAIL
        content_type = resp.headers.get("Content-Type", "")
        if content_type and not content_type.startswith("image/"):
            log_error(f"이미지가 아닌 응답 (Content-Type={content_type})")
            return None, MSG_IMAGE_FAIL
        image = Image.open(BytesIO(resp.content))
        if image.mode != "RGB":
            image = image.convert("RGB")
        buf = BytesIO()
        image.save(buf, "BMP")
        return buf.getvalue()[14:], None
    except Exception as e:
        log_error(f"이미지 다운로드/변환 오류: {e}")
        return None, MSG_IMAGE_FAIL


def GetData(opentalk_name, chat_command, message):
    """
    Instagram URL 명령 핸들러.
    디스패처는 명령 키를 접두사에서만 제거하므로, 재접합 문자열 전체에서
    정규식으로 shortcode를 찾는다 (§4.4).
    어떤 실패에서도 반드시 ("안내문", "text")를 반환한다 — 예외가 새어나가면
    디스패처의 광역 except가 삼켜 방이 무응답이 된다.

    경로: 비로그인 embed(기본) → 실패 시 세션이 있을 때만 instaloader 폴백.
    """
    try:
        shortcode = extract_shortcode(f"{chat_command}{message}")
        if shortcode is None:
            return MSG_UNSUPPORTED, "text"

        thumbnail_url, error = _fetch_thumbnail_url_embed(shortcode)
        if error:
            return error, "text"

        if thumbnail_url is None:
            # embed로 못 얻음. 세션이 있으면 폴백 (비공개 게시물 등), 없으면 여기서 종료.
            loader = get_loader()
            if loader is None:
                return MSG_GONE, "text"
            thumbnail_url, error = _fetch_thumbnail_url(loader, shortcode)
            if error:
                return error, "text"

        dib_bytes, error = _download_dib(thumbnail_url)
        if error:
            return error, "text"

        Helper.CustomPrint(f"✅ Instagram 이미지 준비 완료 ({shortcode}, {len(dib_bytes)} bytes)")
        return dib_bytes, "image"
    except Exception as e:
        log_error(f"미처리 예외 ({type(e).__name__}): {e}")
        return MSG_BAD_RESPONSE, "text"
