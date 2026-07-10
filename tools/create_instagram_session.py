# -*- coding: utf-8 -*-
"""
Instagram 세션 파일 생성 도구 (docs/instagram_기능_복구_작업계획.md §4.3)

선행 조건:
1) 봇(main.py)을 완전히 중지한 뒤 실행할 것.
   봇은 유휴 상태에서도 매 사이클 카카오톡 창을 강제 전면화하고 전역 키 이벤트를
   발사하므로, 이 콘솔에 입력하던 값이 포커스 탈취로 카카오톡 방에 전송될 수 있다.
2) instaloader 4.15.2 이상 (pip install -r requirements.txt).

사용법:
1) 아무 브라우저에서 instagram.com에 로그인한다.
2) 개발자도구(F12) → Application(Chrome) 또는 저장소(Firefox) → Cookies
   → https://www.instagram.com 에서 `sessionid`와 `csrftoken` 두 값을 복사한다.
   (sessionid만으로는 안 된다 — instaloader가 csrftoken으로 X-CSRFToken 헤더를 만든다)
3) 이 스크립트를 실행하고 두 값을 입력한다. 입력값은 화면에 표시되지 않는다.
4) 완료 후 봇을 재시작한다. (세션은 프로세스 시작 시 로드되는 싱글턴이다)

주의: 파일이 생성됐다고 세션이 유효하다는 뜻은 아니다. 잘못된 쿠키도 저장까지는
성공한다. 유효성은 봇 재시작 후 실제 게시물 조회(통합 테스트)로 확정된다.
"""
import getpass
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_KEY_FILE = REPO_ROOT / "config" / "api_key.json"
SESSION_DIR = REPO_ROOT / "saved" / "instagram"


def load_username() -> str:
    # Lib import 금지(§4.3-3): dataManager import는 봇 전체 import 그래프를 끌어온다.
    with open(API_KEY_FILE, encoding="utf-8") as f:
        for entry in json.load(f):
            if entry.get("name") == "IG_USERNAME" and entry.get("key"):
                return entry["key"].strip()
    raise SystemExit(f"[실패] {API_KEY_FILE}에 IG_USERNAME이 없습니다.")


def main() -> None:
    print("=" * 60)
    print("Instagram 세션 파일 생성 도구")
    print("=" * 60)
    print()
    print("!! 봇(main.py)이 실행 중이면 반드시 먼저 종료하세요.")
    print("   실행 중이면 여기 입력하는 값이 카카오톡 방으로 전송될 수 있습니다.")
    print()
    answer = input("봇을 종료했습니까? (y 입력 시 진행): ").strip().lower()
    if answer != "y":
        raise SystemExit("[중단] 봇 종료 후 다시 실행하세요.")

    username = load_username()
    print(f"\n대상 계정: {username}")
    print("브라우저 개발자도구의 instagram.com 쿠키에서 두 값을 복사해 입력하세요.")

    sessionid = getpass.getpass("sessionid: ").strip()
    csrftoken = getpass.getpass("csrftoken: ").strip()
    if not sessionid or not csrftoken:
        raise SystemExit("[실패] sessionid와 csrftoken 둘 다 필요합니다.")

    import instaloader  # 무거운 import는 입력 검증 뒤로

    loader = instaloader.Instaloader(
        sleep=False, request_timeout=10, max_connection_attempts=1,
        download_pictures=False, quiet=True,
    )
    loader.load_session(username, {"sessionid": sessionid, "csrftoken": csrftoken})

    print("\n세션 유효성 확인 중 (test_login)...")
    try:
        who = loader.test_login()
    except Exception as e:
        # test_login은 구 GraphQL 해시를 조회하므로 400/응답 구조 변경에 예외를 낼 수 있다
        print(f"[경고] 검증 요청 실패 ({type(e).__name__}) — 미확정으로 진행합니다.")
        who = None
    # Instagram은 소문자 정규형을 반환하므로 대소문자는 무시하고 비교한다
    if who is not None and who.casefold() != username.casefold():
        raise SystemExit(
            f"[실패] 쿠키의 로그인 계정({who})이 IG_USERNAME({username})과 다릅니다. "
            "올바른 계정으로 로그인한 브라우저에서 쿠키를 복사하세요."
        )
    if who is None:
        print("[경고] 검증 미확정 — 네트워크 오류/요청 제한일 수 있어 무효 단정 불가.")
        print("        '미검증 세션'으로 저장을 진행합니다. 유효성은 통합 테스트에서 확정됩니다.")
        print(f"        주의: 이 경우 쿠키가 정말 {username} 계정의 것인지는 확인되지 않았습니다.")
    else:
        print(f"[확인] 로그인 사용자: {who}")

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    session_file = SESSION_DIR / f"session-{username}"
    loader.save_session_to_file(str(session_file))
    print(f"\n[완료] 세션 파일 저장: {session_file}")
    print("이제 봇을 재시작하면 새 세션이 반영됩니다.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\n[중단]")
