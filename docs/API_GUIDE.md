# 🎮 게임위키 AI API 가이드

로컬 LLM 기반 게임 정보 RAG 서버 — Minecraft, Palworld, Overwatch 2

> ⚠️ **중요 변경사항** (2026-02-18)  
> - ~~`message`~~ → `query` 필드 사용  
> - ~~`game` 파라미터 제거~~ → 질문에 게임명 명시 (예: "마인크래프트 다이아몬드")  
> - 응답 필드: `response` → `answer`

---

## 📡 API 정보

- **Base URL**: `https://awhirl-preimpressive-carina.ngrok-free.dev`
- **엔드포인트**: `POST /api/chat`
- **응답 시간**: 평균 2-5초 (로컬 LLM)
- **데이터**: 나무위키 크롤링 (총 57개 문서, 792만자)

---

## 🔐 보안

⚠️ **현재 상태**: API 키 인증 **지원** (환경변수 설정 시 활성화)

### 옵션 1: API 키 인증 (추천) ✅

**1단계: 서버에 API 키 설정**

```bash
# 환경변수로 API 키 설정 (랜덤 키 생성)
export GAME_WIKI_API_KEY="$(openssl rand -hex 32)"

# 또는 직접 지정
export GAME_WIKI_API_KEY="my-secret-key-12345"

# RAG 서버 시작
cd ~/Work/LLM/rag
source venv/bin/activate
python web.py
```

**2단계: 요청 시 헤더에 키 포함**

```javascript
const response = await fetch('https://awhirl-preimpressive-carina.ngrok-free.dev/api/chat', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': 'my-secret-key-12345'  // 👈 서버와 동일한 키
  },
  body: JSON.stringify({
    query: '마인크래프트 다이아몬드 어디서 구해?',
    session_id: 'user123'
  })
});
```

**키가 없거나 틀리면:**
```json
{
  "error": "Invalid or missing API key",
  "message": "Set X-API-Key header with valid key"
}
```

**키를 설정하지 않으면:**
- API 인증이 비활성화되어 누구나 접근 가능 (현재 기본값)
- 테스트/개발용으로만 사용 권장

### ngrok 기본 인증 (간단)

```bash
# ngrok 실행 시 인증 추가
ngrok http 3334 --basic-auth="username:password"
```

요청 시:
```javascript
const auth = btoa('username:password');
fetch(url, {
  headers: { 'Authorization': `Basic ${auth}` }
});
```

### IP 화이트리스트 (가장 강력)

```python
# web.py에 추가
ALLOWED_IPS = ["123.456.789.0", "192.168.1.100"]

def do_POST(self):
    client_ip = self.client_address[0]
    if client_ip not in ALLOWED_IPS:
        self.send_response(403)
        self.end_headers()
        return
    # ... 기존 코드
```

---

## 🚀 빠른 시작

### Node.js / Express
```javascript
const axios = require('axios');

const API_KEY = process.env.GAME_WIKI_API_KEY || '';  // 환경변수에서 키 읽기

async function askGameWiki(question, sessionId = 'default') {
  try {
    const headers = { 'Content-Type': 'application/json' };
    if (API_KEY) {
      headers['X-API-Key'] = API_KEY;  // 키가 있으면 헤더에 추가
    }
    
    const response = await axios.post(
      'https://awhirl-preimpressive-carina.ngrok-free.dev/api/chat',
      {
        query: question,          // message → query
        session_id: sessionId
      },
      {
        headers: headers,
        timeout: 15000  // 15초 타임아웃
      }
    );
    return response.data.answer;  // response → answer
  } catch (error) {
    console.error('게임위키 API 오류:', error.message);
    return null;
  }
}

// 사용 예시 (질문에 게임명 포함)
const answer = await askGameWiki('마인크래프트 다이아몬드 어떻게 구해?');
console.log(answer);
```

### fetch API
```javascript
const API_KEY = process.env.GAME_WIKI_API_KEY || '';  // 환경변수에서 키 읽기

async function askGameWiki(question, sessionId = 'default') {
  try {
    const headers = { 'Content-Type': 'application/json' };
    if (API_KEY) {
      headers['X-API-Key'] = API_KEY;  // 키가 있으면 헤더에 추가
    }
    
    const response = await fetch(
      'https://awhirl-preimpressive-carina.ngrok-free.dev/api/chat',
      {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ 
          query: question,          // message → query
          session_id: sessionId 
        }),
        signal: AbortSignal.timeout(15000)
      }
    );
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    
    const data = await response.json();
    return data.answer;  // response → answer
  } catch (error) {
    console.error('게임위키 API 오류:', error.message);
    return null;
  }
}
```

### Python
```python
import os
import requests

API_KEY = os.getenv('GAME_WIKI_API_KEY', '')  # 환경변수에서 키 읽기

def ask_game_wiki(question, session_id='default'):
    try:
        headers = {'Content-Type': 'application/json'}
        if API_KEY:
            headers['X-API-Key'] = API_KEY  # 키가 있으면 헤더에 추가
        
        response = requests.post(
            'https://awhirl-preimpressive-carina.ngrok-free.dev/api/chat',
            json={
                'query': question,          # message → query
                'session_id': session_id
            },
            headers=headers,
            timeout=15
        )
        response.raise_for_status()
        return response.json()['answer']  # response → answer
    except Exception as e:
        print(f'게임위키 API 오류: {e}')
        return None

# 사용 예시 (질문에 게임명 포함)
answer = ask_game_wiki('마인크래프트 다이아몬드 어떻게 구해?')
print(answer)
```

---

## 📋 요청/응답 형식

### Request
```json
{
  "query": "마인크래프트 다이아몬드 어디서 구해?",
  "session_id": "user123"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `query` | string | ✅ | 사용자 질문 (게임명 포함 권장) |
| `session_id` | string | ⭕ | 세션 ID (대화 컨텍스트 유지용) |

**중요:**
- ~~`message`~~ → `query` 사용
- ~~`game` 파라미터 제거~~ → 질문에 게임명 명시 (예: "마인크래프트 ...", "오버워치 ...")
- 게임명 없으면 자동 감지 시도 (정확도 낮음)

### Response
```json
{
  "answer": "다이아몬드는 Y 좌표 -64 ~ 16에서 생성됩니다. 가장 많이 나오는 높이는 Y -59입니다.",
  "sources": ["minecraft/다이아몬드", "minecraft/채굴"],
  "session_id": "user123"
}
```

---

## 🎯 게임별 예시

**중요**: 질문에 게임명을 명시하세요!

### Minecraft (19개 문서)
```javascript
await askGameWiki('마인크래프트 다이아몬드 어디서 나와?');
await askGameWiki('마인크래프트 네더 포탈 만드는 법');
await askGameWiki('마인크래프트 엔더 드래곤 잡는 법');
await askGameWiki('마인크래프트 위더 소환 방법');
```

### Palworld (14개 문서)
```javascript
await askGameWiki('팰월드 팰 번식 어떻게 해?');
await askGameWiki('팰월드 고대 문명 파츠 얻는 법');
await askGameWiki('팰월드 아누비스 어디서 잡아?');
```

### Overwatch (24개 문서)
```javascript
await askGameWiki('오버워치 라인하르트 카운터는?');
await askGameWiki('오버워치 머시 궁극기 충전 속도');
await askGameWiki('오버워치 정크랫 스킬 설명');
await askGameWiki('오버워치 겐지 콤보');
```

---

## 🔧 고급 활용

### 1) 캐싱으로 성능 개선
```javascript
const cache = new Map();
const CACHE_TTL = 1000 * 60 * 30; // 30분

async function askGameWikiCached(question, sessionId) {
  const key = question.toLowerCase();  // 질문으로 캐시 키 생성
  const cached = cache.get(key);
  
  if (cached && Date.now() - cached.time < CACHE_TTL) {
    return cached.answer;
  }
  
  const answer = await askGameWiki(question, sessionId);
  if (answer) {
    cache.set(key, { answer, time: Date.now() });
  }
  
  return answer;
}

// 사용
const answer = await askGameWikiCached('마인크래프트 다이아몬드 어디서?', 'user123');
```

### 2) 채팅 봇에 통합
```javascript
// LAMDiceBot 예시
io.on('connection', (socket) => {
  socket.on('chat', async (msg) => {
    const lowerMsg = msg.toLowerCase();
    
    // 게임 키워드 감지 (자동으로 게임명 추가)
    let query = msg;
    if (lowerMsg.includes('마인') || lowerMsg.includes('다이아') || lowerMsg.includes('크리퍼')) {
      if (!lowerMsg.includes('마인크래프트')) {
        query = '마인크래프트 ' + msg;
      }
    } else if (lowerMsg.includes('팰') || lowerMsg.includes('아누비스')) {
      if (!lowerMsg.includes('팰월드')) {
        query = '팰월드 ' + msg;
      }
    } else if (lowerMsg.includes('겐지') || lowerMsg.includes('라인하르트') || lowerMsg.includes('옵치')) {
      if (!lowerMsg.includes('오버워치')) {
        query = '오버워치 ' + msg;
      }
    } else {
      return; // 게임 관련 아니면 무시
    }
    
    const sessionId = socket.id;
    const answer = await askGameWiki(query, sessionId);
    if (answer) {
      socket.emit('ai-response', {
        type: 'game-info',
        answer: answer,
        source: 'GameWiki AI'
      });
    }
  });
});
```

### 3) 에러 처리 + Fallback
```javascript
async function askGameWikiSafe(question, game) {
  try {
    const answer = await askGameWiki(question, game);
    if (!answer) {
      return "죄송합니다. 지금은 게임 정보를 가져올 수 없어요.";
    }
    return answer;
  } catch (error) {
    console.error('게임위키 오류:', error);
    // Fallback: 웹 검색으로 대체
    return await searchWebFallback(question);
  }
}
```

### 4) Rate Limiting (클라이언트 측)
```javascript
class RateLimiter {
  constructor(maxRequests, perMs) {
    this.max = maxRequests;
    this.per = perMs;
    this.requests = [];
  }
  
  async wait() {
    const now = Date.now();
    this.requests = this.requests.filter(t => now - t < this.per);
    
    if (this.requests.length >= this.max) {
      const oldest = this.requests[0];
      const waitMs = this.per - (now - oldest);
      await new Promise(r => setTimeout(r, waitMs));
    }
    
    this.requests.push(Date.now());
  }
}

const limiter = new RateLimiter(5, 60000); // 분당 5회

async function askGameWikiRateLimited(question, game) {
  await limiter.wait();
  return await askGameWiki(question, game);
}
```

---

## ⚠️ 주의사항

### 서버 가용성
- Mac mini M4가 켜져 있어야 작동
- ngrok URL은 재시작 시 변경될 수 있음 (유료 플랜으로 고정 URL 가능)
- 서버 다운 시 대체 로직 필요

### 성능
- 로컬 LLM (Qwen2.5-3B) 기반 → 응답 2-5초
- 동시 요청 많으면 느려짐
- **권장**: 타임아웃 최소 15초 설정

### 정확도
- 나무위키 기반 → 평균 70-80% 정확도
- 키워드 검색 기반 → 애매한 질문은 정확도 낮음
- 참고 자료에 없는 내용은 "정보 없음" 응답

### 보안
- ⚠️ **현재 인증 없음** - URL만 알면 누구나 사용 가능
- **권장**: API 키 또는 IP 화이트리스트 적용
- 민감한 데이터 없음 (공개 게임 정보만)

---

## 🐛 디버깅

### 연결 테스트

**Linux / macOS (인증 없이):**
```bash
curl -X POST https://awhirl-preimpressive-carina.ngrok-free.dev/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"마인크래프트 다이아몬드 어디서 구해?","session_id":"test"}'
```

**Windows PowerShell:**
```powershell
$body = @{
  query = "마인크래프트 다이아몬드 어디서 구해?"
  session_id = "test"
} | ConvertTo-Json

Invoke-RestMethod -Uri "https://awhirl-preimpressive-carina.ngrok-free.dev/api/chat" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

**Windows CMD (curl):**
```cmd
curl -X POST https://awhirl-preimpressive-carina.ngrok-free.dev/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"마인크래프트 다이아몬드 어디서 구해?\",\"session_id\":\"test\"}"
```

**API 키 포함 (Linux/macOS):**
```bash
curl -X POST https://awhirl-preimpressive-carina.ngrok-free.dev/api/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: 93bedb51b1faf8f507813267ce9f268e5b818da82ae90312c3a954f44fcc9599" \
  -d '{"query":"마인크래프트 다이아몬드","session_id":"test"}'
```

**API 키 포함 (Windows CMD):**
```cmd
curl -X POST https://awhirl-preimpressive-carina.ngrok-free.dev/api/chat ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: 93bedb51b1faf8f507813267ce9f268e5b818da82ae90312c3a954f44fcc9599" ^
  -d "{\"query\":\"마인크래프트 다이아몬드\",\"session_id\":\"test\"}"
```

### 일반적인 문제

| 문제 | 원인 | 해결 |
|------|------|------|
| 타임아웃 | LLM 응답 지연 | 타임아웃 15-20초로 증가 |
| 404 에러 | 잘못된 엔드포인트 | `/api/chat` 확인 |
| 빈 응답 | 게임 데이터 없음 | 질문에 게임명 명시 ("마인크래프트 ...", "오버워치 ...") |
| 엉뚱한 답변 | 게임 자동 감지 실패 | 질문 앞에 게임명 붙이기 |
| 연결 실패 | 서버 다운 | Mac mini 상태 확인 또는 @YTRadar 연락 |
| 느린 응답 | 동시 요청 많음 | Rate limiting 추가 또는 캐싱 |
| `message` 필드 오류 | 구버전 API | `message` → `query`로 변경 |

---

## 📊 데이터 현황

### Minecraft (19개 문서)
- 엔더 드래곤, 위더, 네더라이트, 다이아몬드, 레드스톤 등
- 총 193만자

### Palworld (14개 문서)
- 팰 정보, 번식, 고대 문명, 보스 등
- 총 11만자

### Overwatch 2 (24개 문서)
- 영웅 정보, 스킬, 카운터, 궁극기 등
- 총 587만자

**벡터 DB**: 4,172 청크 인덱싱 완료

---

## 🔄 서버 관리

### 서버 시작
```bash
# LLM 서버 (llama-server)
cd ~/Work/LLM
llama-server --model models/qwen2.5-3b-instruct-q4_k_m.gguf \
  --port 8090 --ctx-size 4096 --n-gpu-layers 33 &

# RAG 웹 서버
cd ~/Work/LLM/rag
source venv/bin/activate
python web.py &

# ngrok (외부 접근)
ngrok http 3334 &
```

### 서버 중지
```bash
# 프로세스 확인
ps aux | grep -E "llama-server|web.py|ngrok"

# 종료
pkill -f llama-server
pkill -f web.py
pkill ngrok
```

### 데이터 업데이트
```bash
# 크롤러 실행
cd ~/Work/LLM/crawler
python namu_crawler.py

# 벡터 DB 재생성
cd ~/Work/LLM/rag
source venv/bin/activate
python ingest.py

# RAG 서버 재시작 (새 DB 로드)
pkill -f web.py
python web.py &
```

---

## 📞 문의

- **서버**: Mac mini M4 (이더)
- **Telegram**: @YTRadar
- **GitHub**: on1659
- **프로젝트**: ~/Work/LLM/

---

## 🚧 TODO

- [ ] API 키 인증 구현
- [ ] Rate limiting (서버 측)
- [ ] 캐싱 레이어 추가
- [ ] 로그 시스템
- [ ] 모니터링 대시보드
- [ ] 다국어 지원 (영어)
- [ ] 더 많은 게임 추가

---

**Last Updated**: 2026-02-18  
**Version**: 1.0.0  
**License**: Personal Use Only (공개 배포 금지)
