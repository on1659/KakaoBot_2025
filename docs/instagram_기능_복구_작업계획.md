# Instagram 이미지 전송 기능 복구 작업계획 (v2)

- 최초 작성일: 2026-07-10 (Codex)
- 개정일: 2026-07-10 (v2 — 2개 모델 교차 검증에서 확정된 결함 29건 반영. 이후 v2 자체를 7개 검증자로 재검증해 지적 22건을 추가 반영)
- 대상 기능: Instagram 게시물·릴스 URL 감지 후 대표 이미지 카카오톡 전송
- 관련 코드: `Lib/insta.py`, `Lib/dataManager.py`, `Lib/chat_process.py`, `main.py`, `Lib/Helper.py`

> **v3 정정 (2026-07-10, 구현 중 실측)**
> 구현 후 실제 검증 결과, **비로그인 경로가 살아 있었다.** `/p/<code>/embed/captioned/`를
> `facebookexternalhit` User-Agent로 요청하면 로그인 월 없이 `EmbeddedMediaImage`(대표 이미지)가
> 내려온다. 일반 브라우저 UA로는 로그인 월이 뜨므로 **UA가 결정적**이다. 문제의 릴스
> `DaCr0JyS8-B`, 과거 게시물 `DIpzzT_TBor` 둘 다 세션 없이 이미지 획득·다운로드 성공.
>
> 따라서 §4.2/§4.3의 세션 파일은 **필수가 아니라 선택적 폴백**으로 강등한다. 죽은 것은
> "비로그인 조회" 전체가 아니라 **비로그인 GraphQL 조회**뿐이었다. 아래 §2의 실패 사슬 분석은
> 여전히 정확하지만, §3의 "근본 원인(유일)"은 "instaloader가 쓰는 GraphQL 경로가 비로그인에서
> 막혔고, 로그인으로 우회하려다 로그인마저 차단됐다"로 읽어야 한다.
>
> 현재 구현: **embed(기본, 무인증) → 실패 시 세션이 있을 때만 instaloader 폴백**(비공개 게시물 등).
> 세션이 없어도 공개 게시물·릴스는 정상 동작한다. 계정 차단 위험이 없다는 것이 가장 큰 이득이다.

> **v2 개정 요지**
> 1. "오래된 Instaloader"를 원인 목록에서 제거 — 4.15.x는 로그인 절차를 변경한 적이 없고, 정상 동작하던 2월에도 이미 4.14.1이었다. 업그레이드는 원인 치료가 아니라 부수 작업이다.
> 2. 계획의 전제였던 **세션 파일을 실제로 생성하는 절차**를 신설했다. v1에는 파일을 읽는 절차만 있고 만드는 절차가 없었다.
> 3. v1이 놓친 **실사용 사고 경로**(이미지 실패 시 방 채팅 로그를 방에 도로 붙여넣는 버그, autoUpdate 부팅 루프, 봇 실행 중 세션 도구 사용 시 비밀번호 유출)를 필수 수정에 포함했다.
> 4. §4.7 보안 절은 실제 유출(공개 저장소에 커밋된 GAME_WIKI_API_KEY)에 대응하도록 교체했다.

---

## 1. 작업 목표

중단된 Instagram 이미지 전송 기능을 복구하고, 재실행 때마다 아이디/비밀번호로 로그인하지 않도록 인증 구조를 세션 파일 기반으로 바꾼다.

완료 시 아래를 만족해야 한다.

- 공개 게시물·릴스 URL에서 대표 이미지를 가져와 전송할 수 있다.
- Instagram 로그인 세션을 파일로 저장하고 재시작 후에도 재사용한다.
- 실패 시 원인을 구분한 안내 메시지를 보낸다. 어떤 실패 경로에서도 방의 채팅 내용이 되돌아 전송되지 않는다.
- 봇 배포(커밋/푸시)가 자동 업데이트 로직과 충돌하지 않는다.

## 2. 현상과 실패 사슬

### 확정된 실패 사슬 (saved/log.log 2026-07-06 + 코드 추적)

1. `Instaloader.login()` 호출에 Instagram이 `status:"fail", message:"Unexpected null login result"`를 반환 → `LoginException` (instaloadercontext.py:312).
2. `Lib/insta.py:37`의 광역 `except Exception`이 이 예외를 삼키고 **로그인 안 된 익명 로더를 그대로 반환**한다. `_loader` 싱글턴은 로그인 시도 전에 대입되므로, 실패가 프로세스 수명 동안 캐시되어 재로그인 시도조차 없다.
3. 익명 요청에 Instagram이 `data: null`을 반환 → `structures.py:322-324`의 `["data"]["xdt_shortcode_media"]` 첨자 접근에서 `TypeError: 'NoneType' object is not subscriptable`.
4. `TypeError`는 `InstaloaderException`이 아니므로 `Lib/insta.py:79`의 재시도 분기를 우회, `Lib/insta.py:90`의 광역 `except`가 즉시 `None`을 반환한다. **재시도(insta.py:83-88)는 이 실패 모드에서 한 번도 실행되지 않는다.**
5. `GetData`가 "Not Found Image"를 카카오톡에 전송한다.

### 타임라인

- 2026-02-18 16:07: 로그인 성공(로그 전체에서 유일) 및 마지막 정상 전송. 로그인 코드가 도입된 커밋(c9c2b80)과 같은 날.
- 2026-07-06 18:51: 첫 로그인 실패 기록. **그 사이 코드·라이브러리 변경 없음(계속 4.14.1).**

## 3. 원인 판단

- **근본 원인 (유일)**: Instagram이 이 계정/환경의 자동화 비밀번호 로그인을 거부. `"Unexpected null login result"`는 Instagram 서버 응답이며, 자격증명 오류(`Wrong password`)와 다르다. 봇 재시작마다 비밀번호 로그인을 반복하는 현 구조가 차단을 유발·강화했을 가능성이 높다.
- **공동 결함 (원인의 증폭기)**: 로그인 실패를 삼키고 익명 조회를 계속하는 오류 처리 구조. 실패 원인이 "Not Found Image"로 뭉개져 5개월 가까이 장애를 인지하지 못했다.
- **원인이 아닌 것**: instaloader 버전. 4.15.x 어느 릴리스도 비밀번호 로그인 절차를 변경하지 않았다(4.15: UA/헤더 갱신, 4.15.1: 로그인 상태 프로필 조회 GraphQL 이전, 4.15.2: `Post._obtain_metadata` null 가드). 4.15.2의 null 가드는 위 실패 사슬 4단계의 `TypeError`를 `BadResponseException`으로 바꿀 뿐이며, **가동 중인 봇의 구 코드에 업그레이드만 배포하면** `BadResponseException`이 `InstaloaderException`의 하위 클래스라서 죽어 있던 재시도 루프가 부활해 요청당 최대 15초 이상 추가 정지 + 요청량 3배(차단 위험 증가)만 얻는다. 이 금지는 **구 insta.py 코드가 실행되는 상태**에 대한 것이다 — §9처럼 봇을 중지한 작업 창 안에서 라이브러리를 먼저 올리는 것은 무방하며, 오히려 세션 도구(§4.3)가 신뢰할 수 있는 `test_login()`을 쓰기 위해 필요하다(4.14.1의 `test_login`은 4.15.1에서 폐기된 구 GraphQL 해시 d6f4427f…를 조회한다).

## 4. 작업 범위

### 4.0 [선행·최우선] 유출된 API 키 대응 — 본 기능과 독립, 즉시 수행

`docs/API_GUIDE.md`(추적 파일)에 실제 `GAME_WIKI_API_KEY`가 평문으로 워킹트리 9곳, HEAD 커밋 2곳(c9c2b80) 포함되어 있고, 저장소는 공개(github.com/on1659/KakaoBot_2025)다. `config/api_key.json`의 실키와 동일함을 확인했다.

1. 게임위키 서버에서 해당 키를 폐기하고 새 키를 발급한다. (유출 시점이 지났으므로 문서 수정보다 키 로테이션이 본질이다.)
2. `docs/API_GUIDE.md`의 키 9곳 전부를 `YOUR_API_KEY` placeholder로 치환하고 커밋·푸시한다. 스테이징은 대상 파일만 지정한다(`git add docs/API_GUIDE.md`) — `git add -A`를 쓰면 로컬 수정 상태인 `DefaultSetting.ini`(사설 방 목록)가 공개 저장소로 나간다.
3. 새 키는 `config/api_key.json`(gitignore됨)에만 둔다.
4. git 히스토리 퍼지(filter-repo + force push)는 선택 사항으로 남긴다 — 공개된 지 오래돼 로테이션이 전제이며, 히스토리 퍼지는 클론된 사본을 지우지 못한다.
5. ngrok 고정 도메인(`DefaultSetting.ini:34`, `dataManager.py:77`)은 키와 세트로 노출된 접속 지점이므로, 게임위키 서버 쪽에서 키 인증 강제·요청 제한이 걸려 있는지 확인한다.

### 4.1 의존성 파일 신설 및 버전 관리

현재 저장소에는 requirements.txt/pyproject.toml/Pipfile이 **없다**. 버전 고정 이전에 파일 자체를 신설해야 한다.

- `requirements.txt`를 새로 만들고 전체 런타임 의존성을 기록한다: `instaloader==4.15.2`(목표 버전으로 기재), Pillow, pillow-heif(§4.5 기본안), pywin32, pyautogui, pyperclip, pywinauto, pandas, psutil, requests, openai, pytest(§7) 등.
- 업그레이드 적용은 `pip install -r requirements.txt` 한 번으로 한다. **반드시 봇이 중지된 작업 창(§9-2 이후) 안에서** 수행한다 — §3 "원인이 아닌 것"의 금지는 구 코드가 가동 중인 봇에 대한 것이다.
- 하드코딩된 Chrome 131 User-Agent(`insta.py:26`)는 제거하고 라이브러리 기본값을 쓴다(4.15가 UA를 관리한다).

### 4.2 세션 파일 기반 인증으로 변경

**로더 생성 파라미터 (필수)**: `Instaloader(sleep=False, request_timeout=10, max_connection_attempts=1, download_pictures=False, quiet=True)`로 생성한다. 기본값을 그대로 두면 §4.6 분류층 아래에서 라이브러리 내부 블로킹이 발생해 단일 스레드 봇 전체가 정지한다: ① `sleep=True`(기본)는 **매 요청 전** `do_sleep()`으로 평균 ~1.7초·최대 15초 랜덤 슬립을 건다(instaloadercontext.py:364-367, :411 — §4.8 정지 시간 산정의 전제), ② `request_timeout=300.0`·`max_connection_attempts=3` 기본값은 내부 재시도와 rate-controller 슬립(수 분 가능)으로 §4.6의 "재시도 없음" 규칙을 무력화한다. `max_connection_attempts=1`로 내부 재시도를 끄면 §4.6의 외부 분류·재시도가 유일한 재시도 층이 된다.

인증 순서:

1. 세션 경로는 **저장소 루트 기준**으로 계산한다: `Path(__file__).resolve().parents[1] / 'saved' / 'instagram' / f'session-{username}'` (insta.py 기준). CWD 상대 리터럴을 쓰면 실행 위치에 따라 저장/로드 위치가 갈라진다.
2. 파일이 있으면 `load_session_from_file(username, filename=세션경로)` 로드. **filename 인자를 반드시 명시한다** — 생략 시 기본 경로가 `%LOCALAPPDATA%\Instaloader`라서 문서·운영 절차가 가리키는 위치와 어긋난다. 저장(§4.3) 측도 동일하게 명시한다.
3. `test_login()`은 **로더 생성 시 1회만** 호출한다. 매 URL 처리마다 호출하면 호출당 실제 GraphQL 왕복이 발생해(instaloadercontext.py:242-249) 요청량이 2배가 되고, 이미 차단 이력이 있는 계정의 위험을 키운다.
4. `test_login()` 판정은 **관용적으로** 한다: 반환된 사용자명이 다르면 거부, **None이면 미검증 상태로 세션을 사용**한다. (구현 중 확인: 4.15.2도 test_login은 구 GraphQL 해시 d6f4427f…를 그대로 쓰고 ConnectionException을 None으로 삼킨다 — 4.15.1의 엔드포인트 이전은 test_login을 고치지 않았다. None을 무효로 취급하면 그 엔드포인트가 죽는 순간 유효한 세션까지 영구 거부된다.) 진짜 무효 세션은 첫 게시물 조회의 `LoginRequiredException`이 잡아 로더를 무효화한다(§4.6). 파일이 없거나 계정 불일치면 로더 없음 상태로 두고 안내를 반환한다 — 비밀번호 로그인 폴백 금지(현재 고장난 절차의 재연), 익명 조회 폴백 금지(현재 장애의 재연).
5. **재로드 규칙 (로더 없음/무효 공통)**: `_loader is None`인 모든 상태 — 초기 파일 부재, 시작 검증 실패(일시 네트워크 오류로 `test_login()`이 None이었을 수 있음), 가동 중 `LoginRequiredException`으로 무효화된 경우 — 에서, 다음 URL 처리 시 **마지막 시도로부터 10분 경과 시** 세션 파일 재로드를 시도한다. 이 규칙이 없으면 부팅 시 네트워크 순단 한 번으로 재시작 전까지 기능이 죽는다.

`IG_PASSWORD` 기반 `login()` 호출은 코드에서 제거한다. 단 **`IG_USERNAME`은 유지한다** — 세션 파일 경로 계산과 `load_session_from_file`의 첫 인자로 계속 필요하다. `IG_USERNAME`/`IG_PASSWORD`의 실제 출처는 OS 환경변수가 아니라 `config/api_key.json` → `main.py:56`의 `load_api_keys()`가 `os.environ`에 주입하는 값임을 코드 주석과 운영 문서에 명시한다.

### 4.3 세션 생성 도구 추가 — v1에 없던, 계획 전체가 의존하는 단계

v1은 세션 파일을 읽는 절차만 정의했고 만드는 절차가 없었다. 파일을 쓰는 유일한 API `save_session_to_file()`은 `@_requires_login`이므로, 어떤 방식으로든 로그인된 컨텍스트를 먼저 만들어야 한다.

`tools/create_instagram_session.py` (독립 실행 스크립트):

1. **선행 조건 1: 봇 프로세스를 완전히 중지한다.** 봇은 유휴 상태에서도 매 사이클 카카오톡 창을 강제 전면화하고(`chat_process.py:258-260`), 전역 키 이벤트(Ctrl+V/Enter)를 발사하며, 클립보드를 비우고 덮어쓴다(`chat_process.py:566-580`). 봇이 도는 동안 콘솔에 입력하던 값이 포커스 탈취로 실제 카톡방에 전송될 수 있다. 이 조건을 도구 시작 시 안내문으로도 출력한다.
2. **선행 조건 2: instaloader가 4.15.2로 업그레이드된 상태여야 한다**(§9-4 이후). 4.14.1의 `test_login()`은 폐기된 구 GraphQL 해시를 조회해 유효한 세션도 None으로 판정할 수 있다(§3).
3. `config/api_key.json`을 **직접** 읽어 `IG_USERNAME`을 얻는다(Lib import 금지 — `dataManager` import는 봇 전체 import 그래프와 ini 파싱을 끌어온다). 세션 경로는 §4.2-1과 동일하게 저장소 루트 기준으로 계산한다(`Path(__file__).resolve().parents[1] / 'saved' / 'instagram' / ...`).
4. 운영자가 아무 브라우저에서나 instagram.com에 로그인한 뒤, 개발자도구 → Application/저장소 → Cookies에서 **`sessionid`와 `csrftoken` 두 값을 모두** 복사해 도구에 입력한다(`getpass`로 에코 없이). 두 쿠키는 같은 패널에 있다. **sessionid만으로는 안 된다** — `InstaloaderContext.load_session`(instaloadercontext.py:227)이 `csrftoken` 쿠키를 무조건 읽어 `X-CSRFToken` 헤더를 구성하므로, 없으면 `KeyError('csrftoken')`로 즉사한다. 이 경로는 브라우저에 무관하다. instaloader가 문서화한 자동 쿠키 임포트는 Firefox의 cookies.sqlite 전용이므로 Firefox 사용자는 그 방식을 대안으로 써도 된다. Chrome 쿠키 DB 직접 복호화는 시도하지 않는다(DPAPI/앱바운드 암호화).
5. `L.load_session(username, {"sessionid": ..., "csrftoken": ...})` (4.10+, 설치본에 존재 확인됨) → `L.test_login()` 호출. 판정: **반환값이 `IG_USERNAME`과 다르면 하드 실패**(잘못된 계정의 쿠키). **None이면 "미검증 세션" 경고 후 저장은 진행** — test_login은 네트워크 오류·429도 None으로 뭉개므로(instaloadercontext.py:242-249) None이 곧 무효를 뜻하지 않는다. 주의: `save_session_to_file`의 로그인 검사는 username 플래그만 보므로(instaloader.py:75-80) **잘못된 쿠키도 "저장 성공"까지는 간다** — 파일 생성이 세션 유효를 뜻하지 않으며, 유효성은 §7 통합 테스트에서만 확정된다.
6. `L.save_session_to_file(세션경로)` — **filename 명시**(§4.2와 대칭).
7. 성공/실패 원인만 출력한다. sessionid·csrftoken·비밀번호를 로그와 화면에 남기지 않는다.
8. 종료 후 봇을 재시작해 새 세션을 반영한다(§4.2의 싱글턴 구조 — 도구 실행 중 봇은 선행 조건 1에 따라 항상 중지 상태이므로, 재시작이 유일한 반영 경로다).

비밀번호 로그인(`login()`)은 폴백으로도 두지 않는다. CLI `instaloader --login`도 동일한 `context.login()`을 타므로 현재와 똑같이 실패한다.

### 4.4 URL 처리 보강

- **`www` 없는 URL은 insta.py 정규화로 해결 불가.** 디스패치가 `dataManager.py:137`의 `'https://www.instagram.com/' in msg` 부분문자열 매칭이라 `https://instagram.com/p/...`는 핸들러 호출 자체가 안 된다. `chat_command_Map`에 `'https://instagram.com/'` 키를 추가한다(두 키는 부분문자열이 서로 겹치지 않아 이중 발화 없음).
- **디스패처 수정 (`chat_process.py:841-852`)**: 매치 후 `break`를 추가하되, **긴 키 우선 매칭**을 먼저 적용한다. break만 넣으면 `#modelcheck` 입력이 목록상 앞에 있는 `#model`(dataManager.py:126)에 먼저 걸려 엉뚱한 핸들러 하나만 실행된다(현재는 둘 다 실행되는 버그). 커맨드 맵을 키 길이 내림차순으로 정렬한 뒤 첫 매치에서 break.
- **shortcode 추출**: `split_command`(`chat_process.py:864-872`)는 명령 키가 접두사일 때만 제거하므로 URL이 문장 중간이나 둘째 줄에 있으면 message가 훼손된 형태로 도착한다. `GetData`는 **현행 재접합(`chat_command + message`, insta.py:124)을 유지하고, 그 재접합 문자열 전체에서** 정규식 `https://(www\.)?instagram\.com/(p|reel|reels)/([A-Za-z0-9_-]+)`으로 shortcode를 검색한다. 재접합을 버리고 message만 검색하면 가장 흔한 입력(순수 URL 한 줄 — 이때 message는 접두사가 제거된 `p/<shortcode>/...`)에서 정규식이 실패한다. 쿼리 문자열(igsh, img_index)은 패턴상 자연히 무시된다.
- **미지원 URL 즉시 안내**: shortcode 추출 실패 시 네트워크 요청 없이 "인스타그램 게시물/릴스 링크만 지원합니다"를 반환한다. 현행 동작 참고: 프로필/스토리 URL은 지금도 `extract_shortcode`(insta.py:70)의 ValueError가 광역 except에 잡혀 요청 없이 "Not Found Image"가 나가는 반면, **공유 리디렉션 URL(`/share/p/<token>/`)은 느슨한 정규식(insta.py:55)에 매치돼 무의미한 블로킹 fetch+재시도를 태운다** — 엄격한 정규식이 두 경우 모두 즉시 안내로 정리한다.

### 4.5 이미지 실패가 방을 오염시키지 않도록 계약 변경 — v1이 놓친 실사용 사고

현재 구조의 결정적 버그: `run()`은 명령 처리 직전에 `copy_cheat`로 **방 전체 채팅 로그를 클립보드에 복사**해 둔다. `copy_image_to_clipboard`(`insta.py:100-121`)가 다운로드/디코드에 실패하면 클립보드를 덮지 않은 채 None을 반환하는데, `GetData`(`insta.py:126-132`)는 이를 확인하지 않고 무조건 `("", "image")`를 반환하고, `send_image`(`chat_process.py:495-517`)는 형식 확인 없이 Ctrl+V+Enter를 친다. **결과: 방의 최근 대화 전체가 봇 메시지로 게시된다.** 단일 스레드라 결정론적으로 재현된다.

수정 계약:

- `GetData`는 성공 시 **CF_DIB용 DIB 바이트를 payload로** `(dib_bytes, "image")`를 반환한다. DIB 바이트 = BMP 인코딩 후 앞 14바이트 BITMAPFILEHEADER를 제거한 것(현행 `insta.py:107`의 `output.getvalue()[14:]` 방식 그대로). "BMP 파일 바이트"를 그대로 반환하면 `SetClipboardData(CF_DIB, ...)`에 파일 헤더가 섞여 들어가 깨진 이미지가 게시된다. 클립보드 조작을 핸들러에서 제거하고, `send_image`가 전송 직전에 payload를 클립보드에 올린다. 이 계약은 `docs/스레드_재도입_구현_계획.md`의 `_copy_bmp_to_clipboard(text)` 인터페이스(인자를 그대로 CF_DIB에 넘김)와 동일해 두 계획의 충돌(§4.8)을 해소하고, "지금 복사, 나중에 붙여넣기"의 TOCTOU도 제거한다.
- 다운로드/디코드/변환 실패 시 `(원인별 안내문, "text")`를 반환한다. `("", "image")` 반환 경로를 없앤다.
- `send_image`는 붙여넣기 전 `IsClipboardFormatAvailable(CF_DIB)`를 확인하고, 아니면 **이미지 전송을 중단하고 짧은 텍스트 안내("이미지 전송에 실패했습니다")를 대신 전송**한 뒤 로그를 남긴다(최후 방어선 — 침묵하면 §8의 "모든 실패 경로에 안내 전송" 기준이 성립하지 않는다).
- 클립보드 열기/닫기는 `try/finally`로 보호한다(현재 `insta.py:111` OpenClipboard 이후 예외 시 미해제).
- 이미지 `requests.get`에 **타임아웃 5초**·상태코드·Content-Type 확인을 적용한다.
- **HEIC**: 순정 Pillow는 `.heic`를 디코드하지 못한다. 실제 응답 URL이 `dst-jpg` 변환 파라미터를 포함하므로 대개 JPEG로 오지만, HEIC 원본 대비로 `pillow-heif`를 requirements에 추가하고 **insta.py에서 `pillow_heif.register_heif_opener()`를 호출**한다(설치만으로는 `Image.open`에 연결되지 않는다).

### 4.6 오류 분류 및 재시도 재설계

원칙: **분류가 재시도보다 먼저다.** 현재 `insta.py:79`의 `except InstaloaderException` 광역 캐치는 영구 오류까지 3회(5s+10s) 재시도한다 — 삭제된 게시물은 재시도해도 안 나오고, 429는 재시도할수록 악화되며, 매 재시도가 봇 전체를 얼린다(§4.8).

| 분류 | 판별 | 처리 및 안내문 |
|---|---|---|
| 영구 | `QueryReturnedNotFoundException`(삭제/무효), `PrivateProfileNotFollowedException` | 재시도 없음. "이 게시물은 삭제됐거나 접근할 수 없습니다." |
| 영구(응답 이상) | `BadResponseException` — 삭제/차단뿐 아니라 **응답 구조 변경**(미지의 `__typename` 등, structures.py:325-336)으로도 발생 | 재시도 없음. "게시물을 가져오지 못했습니다." + 원본 예외를 로그에 남겨 라이브러리 업데이트 필요 여부를 판단 |
| 추출 실패 | shortcode 정규식 불일치 | 요청 없음. "인스타그램 게시물/릴스 링크만 지원합니다." |
| 인증 | `LoginRequiredException` | 재시도 없음. 싱글턴 무효화(§4.2-5) + "인스타그램 세션 확인이 필요합니다." |
| 제한 | `ConnectionException` 중 메시지에 `429`/`Too Many Requests` 포함 또는 `__cause__`가 `TooManyRequestsException` | 재시도 없음. "인스타그램 요청 제한에 걸렸습니다. 잠시 후 다시 시도해주세요." |
| 일시 | 그 외 `ConnectionException`, 타임아웃 | **최대 1회 재시도, 백오프 1초.** 최종 실패 시 "일시적인 오류로 이미지를 가져오지 못했습니다." |

- **429는 `TooManyRequestsException` 캐치로 잡을 수 없다.** `get_json`이 내부에서 이 예외를 스스로 잡아(instaloadercontext.py:462) `handle_429` 블로킹 슬립 후 재시도하고, 최종 시도에서는 평범한 `ConnectionException`으로 재포장해 던진다(:464-468). 따라서 ① §4.2의 `max_connection_attempts=1`로 내부 재시도·슬립을 차단하고 ② 위 표처럼 `ConnectionException`의 메시지/`__cause__`로 제한 여부를 판별한다.
- `time.sleep(random.uniform(1, 3))`(insta.py:74)은 제거한다. 매 요청 무조건 1~3초 전체 정지를 만들 뿐 차단 회피 효과가 검증된 바 없다.
- `test_login()` 반환값으로는 **세션 만료와 요청 제한을 구분할 수 없다** — 만료·네트워크 순단·429 모두 동일하게 None을 반환한다(instaloadercontext.py:242-249). 만료/제한 구분은 test_login이 아니라 위 표의 **요청 시 예외 분류**로 한다.
- 사용자 안내문은 위 표의 문안을 쓴다(내부 오류 문자열 비노출).
- 선언만 있고 호출되지 않는 `log_error()`(insta.py:42)는 실제 예외 경로에 연결하거나 삭제한다.

### 4.7 보안 확인 (v1 항목 재분류)

- **[신규·최우선] §4.0의 키 유출 대응** — v1 §4.7이 유일하게 실재하는 유출을 누락했다.
- [확인만] 세션 파일 Git 제외: `saved/`가 이미 .gitignore에 있어 권장 경로 `saved/instagram/`은 자동 제외된다. 신규 규칙 불필요 — 세션 경로가 `saved/` 하위인지만 확인.
- [확인만] `config/api_key.json`, `token.pickle`, `youtube_client_secrets.json` — 이미 gitignore되어 있고 히스토리에 커밋된 적 없음(확인 완료).
- 아이디·비밀번호·sessionid·csrftoken·세션 쿠키를 로그에 남기지 않는다(§4.3-7).
- 무제한 자동 재로그인 금지 — §4.2에서 비밀번호 로그인 자체를 제거했고, 세션 재로드도 10분당 1회로 제한.
- 세션 파일 접근 권한: Windows에서 `os.chmod`는 읽기전용 플래그만 토글할 뿐 접근 주체를 제한하지 못한다. **단일 사용자 PC 전제로 OS 계정 보호에 위임**하는 것으로 문구를 현실화한다(엄격히 하려면 `icacls` 단계를 §9에 추가).

### 4.8 실행 구조 제약과 스레드 계획과의 관계 — v1 미기재

- **이 봇은 단일 스레드다.** `main.py:80-84`의 루프가 방마다 `run()`을 돌리고, 명령 핸들러는 `chat_process.py:847-849`에서 인라인 호출된다. Instagram 링크 하나를 처리하는 동안 5개 방 전체의 폴링·응답이 정지한다.
- 정지 시간 한도: 본 계획의 설정으로 **정상 경로 약 2~4초**(메타데이터 1회 + 이미지 다운로드), **최악(네트워크 무응답) 약 26초** — 메타데이터 10초 타임아웃 × 2회(일시 재시도 1회, §4.6) + 백오프 1초 + 이미지 5초 타임아웃. 이 한도는 §4.2의 `sleep=False`/`request_timeout=10`/`max_connection_attempts=1`과 §4.6의 재시도 삭감이 **전제**다 — 기본값을 그대로 두면 매 요청 전 최대 15초 랜덤 슬립(`do_sleep`)에 내부 재시도·rate-controller 슬립까지 더해져 수 분까지 정지한다. 정지 자체의 근본 해소는 `docs/스레드_재도입_구현_계획.md`의 몫이다.
- **두 계획의 충돌 해소**: 스레드 계획은 `send()`가 DIB 바이트를 받아 `_copy_bmp_to_clipboard`로 복사하는 계약을 전제한다. 본 계획의 §4.5 계약(GetData가 DIB 바이트 반환, 전송자가 클립보드 소유)이 그 전제와 동일하므로, **본 계획을 먼저 반영하고 스레드 계획이 이를 기반으로 진행**한다. 스레드 계획 문서에 이 순서와 payload가 DIB 바이트(파일 헤더 제거)라는 점을 명기하는 상호 참조를 추가한다.

### 4.9 배포 절차 — v1 미기재

- **부팅 루프 주의**: `Helper.py:98`이 로컬/원격 커밋 해시의 **단순 불일치**로 업데이트를 판정하므로, 구현을 로컬 커밋만 하고 푸시하지 않으면 매 기동 `main.py:26-27`이 "재실행해주세요" 후 `sys.exit(0)` — 봇이 영원히 못 뜬다. 작업 기간 동안 `DefaultSetting.ini`의 `autoUpdate = false`로 **로컬만** 변경(커밋 금지)하고, 배포 시 원복한다.
- **배포 = 공개 저장소 푸시**임을 인지한다. origin은 공개 리포지토리이므로 §4.0의 placeholder 치환이 푸시 전에 완료되어 있어야 하고, 커밋은 선택적 스테이징으로 한다(§9-12 — `DefaultSetting.ini` 제외).
- **신규 설정을 `DefaultSetting.ini`에 추가하지 않는다.** 이 파일은 추적 중 + 이 머신에서 로컬 수정 상태 + 매 기동 stash→pull→pop 대상이라 충돌 시 조용히 깨진 설정으로 부팅한다(`Helper.py:168-170`은 pop 실패를 로그만 남김). 본 계획은 신규 ini 키가 **필요 없도록** 설계했다: username은 `api_key.json`에서, 세션 경로는 `saved/instagram/` 고정 관례로 해결한다.

## 5. 구현 대상 파일

| 파일 | 작업 내용 |
|---|---|
| `docs/API_GUIDE.md` | **[최우선]** 실키 9곳 placeholder 치환 (§4.0) |
| `requirements.txt` | **신설** — 전체 의존성 기록, `instaloader==4.15.2`·pytest·pillow-heif 포함 (§4.1/§4.5/§7) |
| `Lib/insta.py` | 세션 로드 전용 `get_loader()`(생성 파라미터·경로 앵커 포함), 오류 분류표, GetData 계약 변경(DIB 바이트 반환), URL 정규식 추출, random sleep 제거, `register_heif_opener()` (§4.2/4.4/4.5/4.6) |
| `Lib/dataManager.py` | `'https://instagram.com/'` 커맨드 키 추가 (§4.4) |
| `Lib/chat_process.py` | 디스패처 긴 키 우선 + break(매칭 로직을 순수 함수로 추출 — §7 테스트 격리), `send_image` payload 계약 + CF_DIB 가드 + 텍스트 폴백 + try/finally (§4.4/4.5) |
| `tools/create_instagram_session.py` | **신설** — 세션 부트스트랩 도구(경로는 저장소 루트 앵커) (§4.3) |
| `tests/` | **신설** — 단위·회귀 테스트 (§7) |
| `docs/스레드_재도입_구현_계획.md` | 본 계획 선행 및 GetData=DIB 바이트 계약 상호 참조 추가 (§4.8) |
| `docs/` | 운영자용 세션 생성·갱신 절차 (§4.3, 봇 중지 선행 조건 포함) |

`DefaultSetting.ini`는 수정하지 않는다(autoUpdate 임시 변경은 로컬 전용, 커밋 금지).

## 6. 권장 처리 흐름

```text
[로더 생성 — 프로세스 시작 시 및 무효화 후 재로드 시]
  세션 파일 존재 확인 → load_session_from_file(username, 경로) → test_login() 1회
  → 유효: 로더 확정 / 무효·부재: 로더 없음 상태 (비밀번호 로그인·익명 폴백 금지)

[URL 감지 시마다]
  재접합 문자열 전체에서 정규식으로 shortcode 추출
    → 실패: "게시물/릴스 링크만 지원" 안내 (네트워크 요청 없음)
  로더 없음 → 마지막 시도로부터 10분 경과 시 세션 파일 재로드 시도(위 [로더 생성] 재진입)
    → 여전히 없음: "세션 설정 필요" 안내
  게시물 메타데이터 요청 → 예외는 §4.6 분류표대로 (영구/인증/제한: 재시도 없음, 일시: 1회)
  이미지 다운로드(5s 타임아웃)·DIB 변환 → 실패: 원인별 안내문을 text로 반환
  성공: (dib_bytes, "image") 반환 → send_image가 클립보드 복사(try/finally) → CF_DIB 확인
    → 확인 실패: 텍스트 안내 폴백 / 성공: 붙여넣기 → 전송
```

세션 검증(test_login)은 URL마다 수행하지 않는다 — 로더 생성 시에만 수행한다(§4.2-3, §4.2-5).

## 7. 테스트 계획

### 준비

- `requirements.txt`에 pytest 포함, `tests/` 디렉터리 신설. 단위 테스트는 이 Windows 개발 머신에서 실행한다(`insta.py`가 최상위에서 win32 모듈을 import하므로 CI 없이 로컬 실행이 기준).
- 네트워크 계층은 모킹한다: `instaloader.Post.from_shortcode`, `requests.get` 패치.
- **ChatProcess 격리**: `__init__`(chat_process.py:39-93)이 즉시 실제 카카오톡 창을 구동하므로 pytest에서 직접 생성할 수 없다. 디스패처 매칭 로직(긴 키 우선 + break)을 `(chat_command_Map, msg)`를 받는 **순수 함수로 추출**해 그 함수를 단위 테스트하고(§5 chat_process.py 행), `send_image` 회귀는 `ChatProcess.__new__`로 인스턴스를 만들어 필요한 속성만 주입 + `send`/`sendtext`를 스파이로 대체해 검증한다.

### 단위 테스트

- shortcode 추출: 게시물/릴스/`www` 없음/쿼리 문자열 포함/문장 중간 URL/둘째 줄 URL/프로필·스토리·공유 리디렉션 URL 거부. 입력은 **디스패처가 실제로 넘기는 형태**(접두사 제거 후 재접합)로 구성한다(§4.4).
- 오류 분류: §4.6 표의 각 행 → 재시도 여부·반환 타입·안내문 검증 (영구/인증/제한 오류에 재시도 0회, 일시 오류에 정확히 1회 확인). 제한 행은 `ConnectionException("... 429 ...")` 메시지 케이스로 검증.
- GetData 계약: 다운로드 실패 모킹 → 반환이 `(안내문, "text")`이고 `"image"`가 아님. 성공 모킹 → payload가 14바이트 헤더 없는 DIB 바이트임을 검증.
- 세션: 파일 부재 → 로더 없음 상태 + 안내 반환, 비밀번호 로그인 미호출 확인. 재로드 스로틀(10분) 동작 확인.

### 회귀 테스트 (검증에서 확인된 버그의 재발 방지)

- **다운로드 실패 시 채팅 로그를 붙여넣지 않는다**: 클립보드에 텍스트를 채워 두고 실패 경로 실행 → 이미지 붙여넣기 미발생 + 텍스트 안내 폴백 발생 확인 (§4.5)
- **`#modelcheck` 단일 발화**: 추출된 매칭 함수에 `#modelcheck` 입력 → `#modelcheck` 핸들러 하나만 반환 (§4.4)
- `www` 없는 URL이 디스패치됨 / 프로필·공유 URL이 네트워크 요청 없이 거절됨
- `#gpt`, `#유툽`, `#radar`, `[카카오맵]` 기존 명령 동작 유지

### 통합 테스트 (수동, 최소 호출 — §9-10 시점)

실 Instagram 호출은 차단 이력이 있는 계정이므로 **시나리오당 1회**로 제한하고 `#테스트방이야`에서, 아래 순서대로 수행한다(순서 중요 — 세션 파일 삭제 테스트가 앞서면 재사용 테스트용 파일이 사라진다):

1. 공개 게시물 1건, 릴스 1건 전송 성공 확인.
2. 삭제된 게시물 1건 → 안내문 확인.
3. 봇 재시작 → 재로그인 없이 세션 재사용 확인.
4. 봇 중지 → 세션 파일 삭제 → 기동 → "세션 설정 필요" 안내 확인 (가동 중 삭제는 싱글턴 특성상 무효과).
5. 봇 중지 → §4.3 도구 재실행으로 세션 복원.

### 배포 후 확인 (§9-13 시점)

- `autoUpdate=true` 원복 + 푸시 완료 상태에서 정상 기동 확인(부팅 루프 부재, §4.9).

## 8. 완료 조건

- `requirements.txt`가 존재하고 instaloader 버전이 고정되어 있다.
- 세션 파일이 `tools/create_instagram_session.py`로 생성되어 있고, 봇 재시작 후 비밀번호 로그인 없이 재사용된다.
- 공개 게시물·릴스 대표 이미지 전송이 각 1회 이상 성공한다(반복 연타 금지 — §7).
- 이미지 획득·처리의 모든 실패 경로에서 `Not Found Image` 대신 원인별 안내가 전송되고(최후 방어선인 CF_DIB 가드 중단 시에는 짧은 실패 안내), **어떤 경우에도 방 채팅 로그가 되돌아 전송되지 않는다**(회귀 테스트 통과).
- 단위·회귀 테스트가 통과한다.
- `docs/API_GUIDE.md`에 실키가 없고, 새 커밋 diff에 민감정보가 없다.
- 배포(푸시) 후 `autoUpdate=true` 상태에서 봇이 정상 기동한다.

## 9. 작업 순서 체크리스트

- [ ] **0. GAME_WIKI_API_KEY 폐기·재발급 + API_GUIDE.md placeholder 치환 + 커밋·푸시** (§4.0 — 다른 모든 작업과 독립, 즉시. 스테이징은 `docs/API_GUIDE.md`만)
- [ ] 1. 작업 시작 시점에 `git tag insta-recovery-base` (롤백 기준선, §10)
- [ ] 2. **봇 중지 (통합 테스트까지 유지)** + `DefaultSetting.ini` `autoUpdate=false` 로컬 변경 (커밋 금지, §4.9)
- [ ] 3. `requirements.txt` 신설 — `instaloader==4.15.2`·pytest·pillow-heif 포함 (§4.1)
- [ ] 4. `pip install -r requirements.txt`로 4.15.2 적용 (봇 중지 상태 — §3의 금지는 가동 중 배포에 대한 것)
- [ ] 5. `tools/create_instagram_session.py` 작성·실행 → 세션 파일 생성 (sessionid+csrftoken, §4.3 — 이 단계는 "파일 생성"까지이고, 세션 유효성 확정은 10번 통합 테스트에서)
- [ ] 6. `Lib/insta.py` 재구조화: 로더 생성 파라미터, 세션 전용 로더+재로드 규칙, 오류 분류, GetData 계약, URL 정규식 (§4.2/4.4/4.5/4.6)
- [ ] 7. `Lib/chat_process.py` 매칭 함수 추출+긴 키 우선+break, `send_image` 가드+폴백, `Lib/dataManager.py` URL 키 (§4.4/4.5)
- [ ] 8. 단위·회귀 테스트 작성·통과 (§7)
- [ ] 9. `docs/스레드_재도입_구현_계획.md` 상호 참조 갱신 (§4.8)
- [ ] 10. 통합 테스트 (테스트방, 시나리오당 1회, §7 순서대로)
- [ ] 11. 운영 문서(세션 갱신 절차, 봇 중지 선행 조건) (§4.3)
- [ ] 12. 커밋 — **선택적 스테이징**(대상: insta.py, chat_process.py, dataManager.py, requirements.txt, tools/, tests/, docs/. `DefaultSetting.ini` 제외)
- [ ] 13. 푸시 → `autoUpdate=true` 원복 → 재기동 확인 (§4.9, §7 배포 후 확인)

## 10. 롤백 계획

- 기준선: 체크리스트 1의 `insta-recovery-base` 태그. 롤백은 insta.py 단일 파일이 아니라 **변경 세트 전체**(insta.py, chat_process.py, dataManager.py, requirements, tools/, tests/)를 태그로 되돌린다. v1처럼 한 파일만 되돌리면 GetData 신계약과 send_image 구계약이 섞여 더 깨진다.
- **환경 롤백 포함**: 코드만 태그로 되돌리면 "구 insta.py + instaloader 4.15.2" 조합이 되는데, 이는 §3이 경고한 죽은 재시도 루프 부활(요청당 ~15초 정지 + 요청량 3배) 조합이다. 롤백 시 `pip install instaloader==4.14.1`을 함께 수행한다.
- 롤백 트리거(명시): ① 실패 경로에서 채팅 로그 에코 재발, ② 배포 후 부팅 루프, ③ Instagram 측 로그인/세션 차단 징후(연속 `LoginRequiredException`), ④ 기존 명령 회귀. 단 **③은 전체 롤백 대신 부분 축소를 우선**한다 — 롤백은 요청 압력을 오히려 늘린다. 부분 축소 = dataManager의 Instagram 명령 등록 2건 주석 처리(다른 명령과 메시지 루프는 영향 없음).
- 세션 파일은 코드와 독립적이므로 롤백 시 삭제할 필요 없다.

## 11. 참고 자료

- Instaloader 릴리스: <https://github.com/instaloader/instaloader/releases>
- Instaloader 로그인 문제 해결(세션 파일 권장): <https://instaloader.github.io/troubleshooting.html#login-error>
- Instaloader 세션 API(`load_session`, `save_session_to_file`): <https://instaloader.github.io/module/instaloader.html>

---

## 부록: v1 대비 반영된 검증 결과 매핑

| 검증 확정 결함 | 반영 위치 |
|---|---|
| 4.15.2 업그레이드는 원인 치료 아님 / 가동 중 선행 배포 시 재시도 루프 부활 | §3, §4.1, §9-4, §10 |
| TypeError가 재시도 분기를 우회하는 실제 메커니즘 | §2 |
| 세션 파일 생성 경로 부재 (v1 최대 공백) | §4.3 |
| `load_session`의 csrftoken 요구 / `save/load` 양쪽 filename 인자 필요 | §4.3-4·6, §4.2-2 |
| `test_login()` 요청별 호출 = 네트워크 왕복 2배 / 4.14.1 test_login 신뢰 불가 | §4.2-3, §4.3-2·5 |
| 만료·검증 실패 시 로더 복구 경로 부재 | §4.2-5, §6 |
| 이미지 실패 시 채팅 로그 에코 | §4.5, §7 회귀 |
| 영구 오류 무차별 재시도 / 429는 ConnectionException으로 재포장됨 | §4.6 |
| `test_login`으로 만료/제한 구분 불가 | §4.6 |
| 라이브러리 내부 재시도·타임아웃 기본값(300s×3회)이 분류층을 무력화 | §4.2, §4.8 |
| 단일 스레드 프리즈 / 스레드 계획 충돌 (payload=DIB 바이트) | §4.8, §4.5 |
| autoUpdate 부팅 루프 / ini stash 충돌 / 선택적 스테이징 | §4.9, §9-12·13 |
| 디스패처 break 부재 + `#model`/`#modelcheck` 이중 발화 | §4.4, §7 회귀 |
| `www` 없는 URL 미도달 / 공유 리디렉션 URL 헛 fetch | §4.4 |
| 문장 중간 URL 훼손 전달 (재접합 문자열에서 정규식 검색) | §4.4 |
| GAME_WIKI_API_KEY 공개 유출 | §4.0 |
| .gitignore 중복 지시 | §4.7 |
| 의존성 파일 부재 / HEIC(pillow-heif + register_heif_opener) | §4.1, §4.5 |
| 테스트 하네스 부재 / ChatProcess 격리 / 라이브 연타 위험 / 통합 테스트 순서 | §7 |
| 롤백 기준선·트리거·환경 롤백 | §10 |
| Windows chmod 무의미 | §4.7 |
| IG_USERNAME 출처 미명시 / 세션 도구 부트스트랩·경로 앵커 | §4.2, §4.3-3 |
| 봇 실행 중 세션 도구 사용 위험 | §4.3-1 |
