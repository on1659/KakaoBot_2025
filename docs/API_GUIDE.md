# 🎮 게임위키 AI API 문서

로컬 LLM 기반 게임 정보 RAG 서버 — 챗봇 통합부터 API 스펙까지 한 곳에서!

> 💡 **안내:** 이 문서의 모든 예시는 **참고용**입니다. 여러분의 챗봇 특성과 사용 목적에 맞게 자유롭게 변형하세요!

---

## 📑 목차

1. [빠른 시작 (3분)](#-빠른-시작-3분)
2. [API 기본 정보](#-api-기본-정보)
3. [보안 설정](#-보안-설정)
4. [대화 연속성 (session_id)](#-대화-연속성-핵심)
5. [실전 예제](#-실전-예제)
   - [Python (카카오톡)](#python-카카오톡-챗봇)
   - [Node.js (디스코드)](#nodejs-디스코드-봇)
   - [Python (텔레그램)](#python-텔레그램-봇---그룹-지원)
   - [JavaScript (웹)](#javascript-웹-채팅)
6. [고급 기능](#-고급-기능)
7. [성능 최적화](#-성능-최적화)
8. [문제 해결](#-문제-해결)
9. [FAQ](#-faq)

---

## 📡 API 기본 정보

- **Base URL**: `https://awhirl-preimpressive-carina.ngrok-free.dev`
- **엔드포인트**: `POST /api/chat`
- **응답 시간**: 평균 2-5초 (로컬 LLM)
- **지원 게임**: 마인크래프트, 오버워치, 팰월드
- **데이터**: 나무위키 크롤링 (총 57개 문서, 792만자)

---

## 🚀 빠른 시작 (3분)

### 1️⃣ API 호출 기본

**Linux/macOS:**
```bash
curl -X POST "https://awhirl-preimpressive-carina.ngrok-free.dev/api/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{
    "query": "마인크래프트 다이아몬드 어디서 구해?",
    "session_id": "user_12345"
  }'
```

**Windows (PowerShell):**
```powershell
$headers = @{
    "Content-Type" = "application/json"
    "X-API-Key" = "YOUR_API_KEY"
}
$body = @{
    query = "마인크래프트 다이아몬드 어디서 구해?"
    session_id = "user_12345"
} | ConvertTo-Json

Invoke-RestMethod -Uri "https://awhirl-preimpressive-carina.ngrok-free.dev/api/chat" `
  -Method POST -Headers $headers -Body $body
```

**Windows (CMD):**
```cmd
curl -X POST "https://awhirl-preimpressive-carina.ngrok-free.dev/api/chat" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: YOUR_API_KEY" ^
  -d "{\"query\":\"마인크래프트 다이아몬드 어디서 구해?\",\"session_id\":\"user_12345\"}"
```

**응답:**
```json
{
  "answer": "다이아몬드는 보루 잔해의 상자에서 종종 나온다...",
  "sources": ["minecraft/마인크래프트_아이템"],
  "session_id": "user_12345"
}
```

### 2️⃣ 핵심 개념

| 항목 | 설명 | 예시 |
|------|------|------|
| **query** | 사용자 질문 (게임명 포함 권장) | "오버워치 한조 궁극기" |
| **session_id** | 대화 연속성 유지용 ID | 사용자 ID, 채팅방 ID 등 |
| **answer** | AI 답변 | "한조는 초자연적인 능력을..." |
| **sources** | 참고 문서 목록 | `["overwatch/한조(오버워치)"]` |

---

## 🔐 보안 설정

### API 키 인증 (선택)

현재 API는 **API 키 인증을 지원**합니다 (환경변수 설정 시 활성화).

#### 서버에 API 키 설정

```bash
# ~/.zshrc 또는 ~/.bashrc에 추가
export GAME_WIKI_API_KEY="YOUR_API_KEY"

# 또는 직접 생성
export GAME_WIKI_API_KEY="$(openssl rand -hex 32)"
```

#### 요청 시 헤더에 키 포함

```javascript
fetch(API_URL, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': 'YOUR_API_KEY'  // 👈 필수
  },
  body: JSON.stringify({...})
});
```

#### 키가 없거나 틀리면

```json
{
  "error": "Invalid or missing API key"
}
```

#### ⚠️ 보안 주의사항

**❌ 절대 하지 마세요:**
```javascript
// 클라이언트 JavaScript에 API 키 노출
const API_KEY = '93bedb...';  // ← 위험!
```

**✅ 올바른 방법:**
```python
# 백엔드 서버에서만 API 호출
@app.route('/ask')
def ask():
    answer = requests.post(API_URL, headers={'X-API-Key': os.getenv('API_KEY')})
    return jsonify(answer)
```

**환경 변수 사용:**
```python
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv('GAME_WIKI_API_KEY')
```

---

## 💬 대화 연속성 (핵심!)

### ✅ 같은 session_id → 대화 이어짐

```python
# 1번째 요청
{"query": "마인크래프트 다이아몬드는?", "session_id": "user_123"}
# → "보루 상자에서 나온다..."

# 2번째 요청 (같은 session_id)
{"query": "어떻게 구해?", "session_id": "user_123"}
# → "다이아몬드는 보루 상자에서..." (맥락 기억!)
```

### ❌ 다른 session_id → 독립 대화

```python
{"query": "어떻게 구해?", "session_id": "user_456"}
# → "여러 게임에 존재합니다. 어떤 게임?" (맥락 없음)
```

### 📌 session_id 설정 팁

> ⚠️ **중요:** 아래 예시는 **권장 사항**입니다. 여러분의 챗봇 특성에 맞게 자유롭게 조정하세요!

**1:1 채팅봇:**
```python
session_id = f"user_{user_id}"  # 사용자별 독립 대화
```

**그룹 채팅봇 - 패턴 A (개인별 세션, 추천):**

```python
session_id = f"group_{group_id}_user_{user_id}"
# A: "한조 알려줘" → A만의 세션
# B: "겐지 알려줘" → B만의 세션 (A와 독립!)
```
**장점:** 각자 독립된 대화 가능  
**단점:** 그룹 전체가 같은 주제를 논의할 때 불편

**그룹 채팅봇 - 패턴 B (전체 공유 세션):**

```python
session_id = f"group_{group_id}"
# 모두가 하나의 대화 맥락 공유
```
**장점:** 팀 단위 질문-답변에 유용  
**단점:** 여러 주제 동시 진행 시 혼란

**그룹 채팅봇 - 패턴 C (주제별 세션, 고급):**

```python
# 사용자가 명시적으로 세션 선택
if message.startswith("!새대화"):
    session_id = f"group_{group_id}_{timestamp}"
else:
    session_id = current_session_id  # 기존 세션 유지
```
**장점:** 유연성 최대화  
**단점:** 구현 복잡도 증가

**웹 채팅:**
```python
session_id = f"web_{uuid.uuid4()}"  # 브라우저 세션별
```

### 💡 선택 가이드

| 상황 | 추천 패턴 |
|------|----------|
| 개인용 공부 챗봇 | 패턴 A (개인별) |
| 게임 길드/팀 챗봇 | 패턴 B (전체 공유) |
| 고객 지원 봇 | 패턴 A (개인별) |
| 프로젝트 협업 봇 | 패턴 C (주제별) |

**핵심 원칙:** `session_id`는 **단순한 문자열**입니다. 여러분의 사용 사례에 맞게 어떤 형식이든 자유롭게 만드세요!

---

## 🎭 그룹 채팅 시나리오 비교

### ❌ 잘못된 구현 (그룹 전체 세션)

```python
# 모든 사용자가 같은 session_id 사용
session_id = f"group_{chat_id}"
```

**문제 발생:**
```
👤 철수: 오버워치 한조 알려줘
🤖 AI: 한조는 시마다 일족의 암살자입니다...

👤 영희: 마인크래프트 다이아몬드는?
🤖 AI: 다이아몬드는 보루 상자에서...

👤 철수: 궁극기는?
🤖 AI: 다이아몬드의 궁극기는... ❌ (한조 궁극기를 물은 건데!)

👤 영희: 어떻게 구해?
🤖 AI: 한조는 상점에서... ❌ (다이아몬드 획득법을 물은 건데!)
```

**원인:** 모두가 같은 세션을 공유해서 대화가 뒤섞임!

### ✅ 올바른 구현 (개인별 세션)

```python
# 각 사용자마다 다른 session_id
session_id = f"group_{chat_id}_user_{user_id}"
```

**정상 작동:**
```
👤 철수: 오버워치 한조 알려줘
🤖 AI: 한조는 시마다 일족의 암살자입니다...

👤 영희: 마인크래프트 다이아몬드는?
🤖 AI: 다이아몬드는 보루 상자에서...

👤 철수: 궁극기는?
🤖 AI: 한조의 궁극기는 용의 일격입니다... ✅

👤 영희: 어떻게 구해?
🤖 AI: 다이아몬드는 Y좌표 -64~16에서... ✅
```

**핵심:** 각자 독립된 대화 맥락 유지!

---

## 🛠️ 실전 예제

> 📝 **참고:** 아래 예시는 **하나의 구현 방법**입니다. 여러분의 환경에 맞게 수정해서 사용하세요!

### Python (카카오톡 챗봇)

```python
import requests
import json

API_URL = "https://awhirl-preimpressive-carina.ngrok-free.dev/api/chat"
API_KEY = "YOUR_API_KEY"

def ask_game_wiki(user_message, user_id):
    """게임위키 AI에게 질문"""
    payload = {
        "query": user_message,
        "session_id": f"kakao_{user_id}"  # 카카오 사용자ID로 세션 관리
    }
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    try:
        response = requests.post(API_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data["answer"]
    except requests.exceptions.Timeout:
        return "⏱️ 응답 시간 초과 (30초). 다시 시도해주세요."
    except Exception as e:
        return f"❌ 오류 발생: {e}"

# 카카오톡 스킬 핸들러
@app.route("/skill", methods=["POST"])
def kakao_skill():
    req = request.json
    user_msg = req["userRequest"]["utterance"]
    user_id = req["userRequest"]["user"]["id"]
    
    answer = ask_game_wiki(user_msg, user_id)
    
    return jsonify({
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": answer}}]
        }
    })
```

### Node.js (디스코드 봇)

```javascript
const axios = require('axios');
const { Client, GatewayIntentBits } = require('discord.js');

const API_URL = 'https://awhirl-preimpressive-carina.ngrok-free.dev/api/chat';
const API_KEY = 'YOUR_API_KEY';

async function askGameWiki(query, sessionId) {
  try {
    const response = await axios.post(API_URL, 
      { query, session_id: sessionId },
      { 
        headers: { 
          'Content-Type': 'application/json',
          'X-API-Key': API_KEY 
        },
        timeout: 30000
      }
    );
    return response.data.answer;
  } catch (error) {
    if (error.code === 'ECONNABORTED') {
      return '⏱️ 응답 시간 초과. 다시 시도해주세요.';
    }
    return `❌ 오류: ${error.message}`;
  }
}

const client = new Client({ 
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent] 
});

client.on('messageCreate', async (message) => {
  if (message.author.bot) return;
  
  // "!게임 질문" 형식
  if (message.content.startsWith('!게임 ')) {
    const query = message.content.slice(4);
    
    // ✅ 그룹 채널: 개인별 세션 관리 (추천)
    const sessionId = `discord_${message.channel.id}_user_${message.author.id}`;
    
    const answer = await askGameWiki(query, sessionId);
    await message.reply(answer);
  }
});

client.login('YOUR_BOT_TOKEN');
```

**왜 이렇게 해야 하나요?**

```javascript
// ❌ 채널별 세션 (문제 발생)
const sessionId = `discord_${message.channel.id}`;

// 시나리오:
// - 철수: "!게임 오버워치 한조"
// - AI: "한조는 초자연적인 능력을..."
// - 영희: "!게임 궁극기는?" 
// - AI: "한조의 궁극기는..." (← 영희가 한조를 안 물어봤는데!)

// ✅ 개인별 세션 (올바른 방법)
const sessionId = `discord_${message.channel.id}_user_${message.author.id}`;

// 시나리오:
// - 철수: "!게임 오버워치 한조"
// - AI: "한조는 초자연적인 능력을..."
// - 영희: "!게임 궁극기는?" 
// - AI: "여러 게임에 존재합니다. 어떤 게임?" (← 영희 세션은 독립!)
```

### Python (텔레그램 봇 - 그룹 지원)

```python
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

API_URL = "https://awhirl-preimpressive-carina.ngrok-free.dev/api/chat"
API_KEY = "YOUR_API_KEY"

def ask_game_wiki(query: str, session_id: str) -> str:
    """게임위키 AI에게 질문"""
    payload = {"query": query, "session_id": session_id}
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    try:
        response = requests.post(API_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()["answer"]
    except requests.exceptions.Timeout:
        return "⏱️ 응답 시간 초과 (30초). 다시 시도해주세요."
    except Exception as e:
        return f"❌ 오류: {e}"

async def game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """그룹/개인 채팅 모두 지원"""
    user_query = " ".join(context.args)
    if not user_query:
        await update.message.reply_text("사용법: /게임 질문내용")
        return
    
    # ✅ 그룹 채팅: 개인별 세션 관리
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if update.effective_chat.type in ['group', 'supergroup']:
        # 그룹: chat_id + user_id 조합
        session_id = f"telegram_group_{chat_id}_user_{user_id}"
    else:
        # 개인 채팅: user_id만 사용
        session_id = f"telegram_user_{user_id}"
    
    answer = ask_game_wiki(user_query, session_id)
    await update.message.reply_text(answer)

def main():
    app = Application.builder().token("YOUR_BOT_TOKEN").build()
    app.add_handler(CommandHandler("게임", game_command))
    app.run_polling()

if __name__ == '__main__':
    main()
```

**실제 사용 예시 (텔레그램 그룹):**

```
👤 철수: /게임 오버워치 한조
🤖 AI: 한조는 초자연적인 능력을 사용하는 영웅입니다...

👤 영희: /게임 겐지는?
🤖 AI: 겐지는 시마다 일족의...

👤 철수: /게임 궁극기는?
🤖 AI: 한조의 궁극기는... (← 철수의 이전 대화 맥락 유지!)

👤 영희: /게임 궁극기는?
🤖 AI: 겐지의 궁극기는... (← 영희의 이전 대화 맥락 유지!)
```

**session_id 구조:**
- 철수: `telegram_group_-123456789_user_111111`
- 영희: `telegram_group_-123456789_user_222222`
- → 같은 그룹이지만 **각자 독립된 대화!**

### JavaScript (웹 채팅)

```javascript
// 브라우저 세션ID 생성 (최초 1회)
let sessionId = localStorage.getItem('game_wiki_session');
if (!sessionId) {
  sessionId = 'web_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  localStorage.setItem('game_wiki_session', sessionId);
}

async function askGameWiki(query) {
  const response = await fetch('https://awhirl-preimpressive-carina.ngrok-free.dev/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': 'YOUR_API_KEY'
    },
    body: JSON.stringify({
      query: query,
      session_id: sessionId
    })
  });
  
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  
  const data = await response.json();
  return data.answer;
}

// 사용 예시
document.getElementById('sendBtn').addEventListener('click', async () => {
  const userInput = document.getElementById('userInput').value;
  const answer = await askGameWiki(userInput);
  displayMessage('AI', answer);
});
```

---

## 🎯 고급 기능

### 1️⃣ 오타 자동 보정

사용자가 "오버워치 칸조"라고 입력하면:
```json
{
  "answer": "🔍 혹시 '오버워치 한조'를 찾으시나요?\n\n한조는 초자연적인 능력을...",
  "sources": ["overwatch/한조(오버워치)"]
}
```

→ **자동으로 보정된 키워드로 재검색해서 답변!**

### 2️⃣ 게임 선택 (다중 게임 감지)

"다이아몬드"처럼 여러 게임에 존재하는 키워드:
```json
{
  "answer": "'다이아몬드'은(는) 여러 게임에 존재합니다. 어떤 게임에 대해 알고 싶으신가요?",
  "sources": [],
  "ask_game": true,
  "games": ["마인크래프트", "팰월드"]
}
```

→ **사용자에게 게임 선택 요청**

후속 질문:
```json
{"query": "마인크래프트", "session_id": "same_session"}
```

→ **마인크래프트 다이아몬드 정보 출력**

### 3️⃣ 세션 관리 및 초기화

#### 세션 자동 만료

서버는 **마지막 대화 후 30분**이 지나면 세션을 자동으로 만료시킵니다.

```python
# 30분 후 같은 session_id로 요청하면
{"query": "안녕?", "session_id": "user_123"}
# → 이전 대화 맥락이 사라진 새 대화로 시작
```

#### 수동 세션 리셋

대화를 처음부터 다시 시작하려면:

**방법 1: 타임스탬프 추가 (추천)**
```python
import time

# 사용자가 "새 대화" 명령 입력 시
session_id = f"user_{user_id}_{int(time.time())}"
```

**방법 2: 카운터 증가**
```python
# 전역 카운터 또는 DB에 저장
session_counter = get_user_session_counter(user_id)
session_counter += 1
session_id = f"user_{user_id}_v{session_counter}"
```

**방법 3: UUID 사용**
```python
import uuid

# 완전히 새로운 세션
session_id = f"user_{user_id}_{uuid.uuid4().hex[:8]}"
```

#### 컨텍스트 오버플로 방지

현재 서버는 **최근 5개 메시지**만 LLM에 전달하지만, 세션 자체는 계속 쌓입니다.

**문제:**
- 1000턴 대화 → DB/메모리 부담
- 너무 긴 대화는 맥락이 오히려 방해

**해결책 (챗봇 측):**

```python
class ChatBot:
    def __init__(self):
        self.turn_count = {}  # user_id → 대화 턴 수
    
    def ask(self, user_id, query):
        # 현재 세션 ID
        session_id = f"user_{user_id}"
        
        # 턴 수 증가
        self.turn_count[user_id] = self.turn_count.get(user_id, 0) + 1
        
        # 20턴 이상이면 세션 리셋
        if self.turn_count[user_id] >= 20:
            session_id = f"user_{user_id}_{int(time.time())}"
            self.turn_count[user_id] = 0
            print(f"[세션 리셋] {user_id} - 20턴 초과")
        
        # API 호출
        response = requests.post(API_URL, json={
            "query": query,
            "session_id": session_id
        })
        return response.json()["answer"]
```

**또는 시간 기반:**
```python
# 1시간마다 세션 리셋
session_id = f"user_{user_id}_{int(time.time() // 3600)}"
```

**주제별 세션 (고급):**
```python
# 사용자가 명시적으로 주제 변경
if "새로운 주제" in query or "다른 게임" in query:
    session_id = f"user_{user_id}_{uuid.uuid4().hex[:8]}"
    await message.reply("새로운 대화를 시작합니다! 🔄")
```

#### 세션 수명 주기 요약

```
1. 생성: 첫 API 요청 시
2. 유지: 30분 내 계속 대화 시
3. 만료: 30분 동안 요청 없음
4. 수동 리셋: session_id 변경 시
```

**Best Practice:**
- **일반 대화**: 자동 만료(30분) 활용
- **긴 대화**: 10-20턴마다 수동 리셋
- **주제 변경**: 사용자 요청 시 리셋
- **그룹 채팅**: 개인별 + 시간 기반 조합

---

## ⚠️ 에러 처리

### 타임아웃 처리

```python
try:
    response = requests.post(API_URL, json=payload, timeout=30)
except requests.exceptions.Timeout:
    return "응답 시간이 너무 오래 걸립니다. 잠시 후 다시 시도해주세요."
```

### HTTP 에러

```python
try:
    response.raise_for_status()
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 401:
        return "API 키가 유효하지 않습니다."
    elif e.response.status_code == 500:
        return "서버 오류입니다. 잠시 후 다시 시도해주세요."
    else:
        return f"오류 발생 ({e.response.status_code})"
```

### 빈 응답 처리

```python
data = response.json()
if not data.get("answer"):
    return "답변을 생성할 수 없습니다. 질문을 다시 입력해주세요."
```

---

## 📊 성능 최적화

### 1️⃣ 응답 시간 단축

- **게임명 명시**: "한조" → "오버워치 한조" (검색 정확도 ↑)
- **구체적 질문**: "정보" → "궁극기 알려줘" (관련 문서만 검색)

### 2️⃣ 동시 요청 제한

```python
import asyncio
from aiohttp import ClientSession

# 동시 최대 3개 요청
semaphore = asyncio.Semaphore(3)

async def ask_with_limit(query, session_id):
    async with semaphore:
        async with ClientSession() as session:
            async with session.post(API_URL, json={...}) as resp:
                return await resp.json()
```

### 3️⃣ 캐싱 (선택)

자주 묻는 질문은 캐싱:
```python
import redis
r = redis.Redis()

def ask_with_cache(query, session_id):
    cache_key = f"qa:{query}"
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)
    
    answer = ask_game_wiki(query, session_id)
    r.setex(cache_key, 3600, json.dumps(answer))  # 1시간 캐시
    return answer
```

---

## 🔐 보안

### API 키 관리

**❌ 절대 하지 마세요:**
```javascript
// 클라이언트 JavaScript에 API 키 노출
const API_KEY = '93bedb...';  // ← 위험!
```

**✅ 올바른 방법:**
```javascript
// 백엔드 서버에서만 API 호출
app.post('/ask', async (req, res) => {
  const answer = await askGameWiki(req.body.query, req.session.id);
  res.json({ answer });
});
```

### 환경 변수 사용

```bash
# .env
GAME_WIKI_API_KEY=YOUR_API_KEY
GAME_WIKI_API_URL=https://awhirl-preimpressive-carina.ngrok-free.dev/api/chat
```

```python
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv('GAME_WIKI_API_KEY')
```

---

## 🧪 테스트 시나리오

### 1️⃣ 기본 질문

```bash
curl -X POST "API_URL" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"query":"오버워치 겐지 궁극기","session_id":"test1"}'
```
**기대:** 겐지 궁극기 정보 출력

### 2️⃣ 후속 질문

```bash
# 1번째
curl ... -d '{"query":"마인크래프트 다이아몬드","session_id":"test2"}'
# 2번째 (같은 session_id)
curl ... -d '{"query":"어떻게 구해?","session_id":"test2"}'
```
**기대:** 다이아몬드 구하는 법 출력 (맥락 유지)

### 3️⃣ 오타 보정

```bash
curl ... -d '{"query":"오버워치 칸조","session_id":"test3"}'
```
**기대:** "혹시 '한조'를 찾으시나요?" + 한조 정보

---

## 📞 문제 해결

### "응답을 생성할 수 없습니다"

**원인:**
- LLM 서버 다운
- 검색 결과 없음

**해결:**
1. 게임명을 명시: "한조" → "오버워치 한조"
2. 질문을 구체화: "정보" → "궁극기 알려줘"

### 타임아웃 (30초 초과)

**원인:**
- 서버 과부하
- 네트워크 지연

**해결:**
```python
# 재시도 로직
for attempt in range(3):
    try:
        return ask_game_wiki(query, session_id)
    except Timeout:
        if attempt == 2:
            return "서버 응답 없음"
        time.sleep(2 ** attempt)  # 지수 백오프
```

### 대화가 이어지지 않음

**원인:**
- session_id가 매번 다름

**해결:**
```python
# ❌ 잘못된 예
session_id = f"user_{uuid.uuid4()}"  # 매번 새 ID 생성

# ✅ 올바른 예
session_id = f"user_{user_id}"  # 사용자별 고정 ID
```

---

## 📚 참고 자료

- **전체 API 문서**: `API_GUIDE.md`
- **GitHub 저장소**: `on1659/RadarCustomLLM_Game`
- **서버 상태**: `https://awhirl-preimpressive-carina.ngrok-free.dev/api/chat` (POST)

---

## 💡 FAQ

**Q: 무료로 사용 가능한가요?**
A: 현재는 개인 프로젝트용 무료 제공. 상업적 이용은 문의 필요.

**Q: 응답 속도는?**
A: 평균 2-5초 (질문 복잡도에 따라 다름)

**Q: 지원 게임은?**
A: 마인크래프트, 오버워치, 팰월드 (추가 예정)

**Q: 한국어만 지원?**
A: 현재 한국어 전용. 영어/일본어는 일부만 인식.

**Q: 세션은 언제까지 유지?**
A: 마지막 대화 후 30분간 유지 (이후 자동 만료)

---

## 🎨 자유롭게 활용하세요!

이 가이드의 모든 예시는 **참고용**입니다. 여러분의 챗봇 특성에 맞게 자유롭게 변형하세요!

### 🔧 커스터마이징 예시

**게임 길드봇:**
```python
# 길드 전체가 같은 레이드 공략을 논의
session_id = f"guild_{guild_id}_raid"
```

**학습 도우미봇:**
```python
# 과목별로 다른 세션
session_id = f"student_{user_id}_subject_{subject_name}"
```

**멀티 게임 지원:**
```python
# 게임마다 독립된 대화
if "마인크래프트" in query:
    session_id = f"user_{user_id}_minecraft"
elif "오버워치" in query:
    session_id = f"user_{user_id}_overwatch"
```

**타임아웃 세션:**
```python
# 30분 후 자동 초기화
session_id = f"user_{user_id}_{int(time.time() // 1800)}"
```

### 💬 피드백 환영!

- 더 나은 활용법이 있다면 공유해주세요!
- 문제가 발생하면 GitHub Issue로 알려주세요
- 여러분의 창의적인 활용 사례를 기다립니다

**Remember:** API는 도구일 뿐입니다. 어떻게 사용할지는 **여러분의 상상력**에 달려있습니다! 🚀

---

**🎮 Happy Coding!**