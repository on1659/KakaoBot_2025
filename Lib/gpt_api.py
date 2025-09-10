import os
import openai
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import json_data_manager  # 같은 패키지 내 모듈로 가정
from . import dataManager  # 같은 패키지 내 모듈로 가정

# 1) OpenAI API Key 설정
openai.api_key = os.environ.get("OPENAI_API_KEY")
GPT_MAX_TOKEN = int(dataManager.GPT_MAX_TOKEN)

# API 사용량 모니터링을 위한 파일 경로
USAGE_LOG_FILE = Path(__file__).parent.parent / "config" / "api_usage.json"

def load_usage_data():
    """API 사용량 데이터를 로드합니다."""
    if USAGE_LOG_FILE.exists():
        try:
            with open(USAGE_LOG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass
    return {
        "daily_usage": {},
        "total_requests": 0,
        "last_reset": datetime.now().strftime("%Y-%m-%d")
    }

def save_usage_data(data):
    """API 사용량 데이터를 저장합니다."""
    try:
        with open(USAGE_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"사용량 데이터 저장 실패: {e}")

def log_api_usage(model_name, prompt_length, response_length):
    """API 사용량을 로깅합니다."""
    data = load_usage_data()
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 일일 사용량 초기화 (새로운 날이면)
    if data["last_reset"] != today:
        data["daily_usage"] = {}
        data["last_reset"] = today
    
    # 오늘 사용량 업데이트
    if today not in data["daily_usage"]:
        data["daily_usage"][today] = {
            "requests": 0,
            "total_tokens": 0,
            "models": {}
        }
    
    data["daily_usage"][today]["requests"] += 1
    data["daily_usage"][today]["total_tokens"] += prompt_length + response_length
    data["total_requests"] += 1
    
    if model_name not in data["daily_usage"][today]["models"]:
        data["daily_usage"][today]["models"][model_name] = 0
    data["daily_usage"][today]["models"][model_name] += 1
    
    save_usage_data(data)

def get_usage_summary():
    """API 사용량 요약을 반환합니다."""
    data = load_usage_data()
    today = datetime.now().strftime("%Y-%m-%d")
    
    if today in data["daily_usage"]:
        today_usage = data["daily_usage"][today]
        summary = f"📊 API 사용량 현황\n"
        summary += f"오늘 요청 수: {today_usage['requests']}회\n"
        summary += f"오늘 토큰 수: {today_usage['total_tokens']:,}개\n"
        summary += f"총 요청 수: {data['total_requests']:,}회\n\n"
        
        if today_usage["models"]:
            summary += "사용된 모델:\n"
            for model, count in today_usage["models"].items():
                summary += f"- {model}: {count}회\n"
        
        return summary
    else:
        return "📊 API 사용량 현황\n오늘은 아직 API를 사용하지 않았습니다."


def getData(opentalk_name: str, chat_command: str, user_prompt: str):
    """
    채팅방 이름(opentalk_name)과 명령어(chat_command), 사용자 프롬프트(user_prompt)를 받아
    DB/JSON에서 GPT 모델을 조회한 후 ask_gpt 함수를 호출하여 (응답, 메시지타입)을 반환.
    """
    # JSON에서 꺼낸 모델 이름이 None 이면 설정 파일의 기본값 사용
    model_name = json_data_manager.get_chatroom_data(opentalk_name, "gpt_model") or dataManager.GPT_DEFAULT_MODEL
    return ask_gpt(user_prompt, model_name)

def ask_gpt(prompt: str, model_name: str = None):
    """
    사용자 프롬프트(prompt)와 모델 이름(model_name)을 받아,
    OpenAI Chat API를 호출 후 (응답문자열, "text") 를 반환.
    """
    # model_name이 None이면 설정 파일의 기본값 사용
    if model_name is None:
        model_name = dataManager.GPT_DEFAULT_MODEL
    
    # 답변 길이 제한 문구를 프롬프트에 추가
    prompt_with_limit = f"{prompt}\n\n{dataManager.GPT_ANSWER_LENGTH_LIMIT}"
    
    try:
        # prompt = f"{prompt}\n\n답변은 반드시 {GPT_MAX_TOKEN} 토큰보다 짧게 해줘."
        # API 호출 시도 (temperature 오류 시 자동으로 1.0으로 재시도)
        resp = None
        
        # gpt-5-nano는 temperature=1.0만 지원하며, max_completion_tokens를 200으로 설정
        if "gpt-5-nano" in model_name:
            # gpt-5-nano는 테스트에서 성공한 설정을 그대로 사용
            resp = openai.chat.completions.create(
                model = model_name,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user",   "content": prompt_with_limit}
                ],
                temperature=1.0,
                max_completion_tokens=1000,
                reasoning_effort="minimal"
            )
            
            # gpt-5-nano가 빈 응답을 반환하는 경우 gpt-4o-mini로 fallback
            if resp.choices[0].message.content is None or resp.choices[0].message.content.strip() == "":
                print(f"gpt-5-nano가 빈 응답을 반환했습니다. gpt-4o-mini로 전환합니다.")
                resp = openai.chat.completions.create(
                    model = "gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user",   "content": prompt_with_limit}
                    ],
                    temperature=0.7,
                    max_completion_tokens=GPT_MAX_TOKEN,
                )
        else:
            # 다른 모델들은 기존 로직 사용
            temp_values = [0.7, 1.0]  # 먼저 0.7 시도, 실패하면 1.0 시도
            max_completion_tokens_to_use = GPT_MAX_TOKEN
            
            for temp_value in temp_values:
                try:
                    resp = openai.chat.completions.create(
                        model = model_name,
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant."},
                            {"role": "user",   "content": prompt_with_limit}
                        ],
                        temperature=temp_value,
                        max_completion_tokens = max_completion_tokens_to_use,
                    )
                    break  # 성공하면 루프 종료
                except openai.APIError as e:
                    if "temperature" in str(e) and temp_value == 0.7:
                        # temperature 오류이고 0.7을 시도한 경우, 1.0으로 재시도
                        continue
                    else:
                        # 다른 오류이거나 이미 1.0을 시도한 경우, 예외를 다시 발생
                        raise e
        
        if resp is None:
            raise Exception("API 호출에 실패했습니다.")
        
        # openai>=1.0.0 에서는 resp.choices[0].message.content
        if not resp.choices or len(resp.choices) == 0:
            raise Exception("API 응답에 choices가 없습니다.")
        
        answer = resp.choices[0].message.content
        if answer is not None:
            answer = answer.strip()
        else:
            answer = ""
        
        # API 사용량 로깅
        try:
            log_api_usage(model_name, len(prompt), len(answer))
        except Exception as e:
            print(f"사용량 로깅 실패: {e}")
        
        max_chars = GPT_MAX_TOKEN * 2  # 한글 기준 대략치
        show_limit_notice = len(answer) >= int(max_chars * 0.9)
        if show_limit_notice:
            text = f'질문하신 "{prompt}"에 대한 답변입니다. 최대 약 {max_chars}자까지 답변이 가능합니다.\n- {answer}'
        else:
            text = f'질문하신 "{prompt}"에 대한 답변입니다.\n- {answer}'
        return text, "text"
    
    except openai.RateLimitError as e:
        error_msg = "OpenAI API 할당량을 초과했습니다. 관리자에게 문의하거나 잠시 후 다시 시도해주세요."
        print(f"RateLimitError: {e}")
        return error_msg, "text"
    
    except openai.APIError as e:
        error_msg = f"OpenAI API 오류가 발생했습니다: {str(e)}"
        print(f"APIError: {e}")
        return error_msg, "text"
    
    except Exception as e:
        error_msg = f"예상치 못한 오류가 발생했습니다: {str(e)}"
        print(f"Unexpected error: {e}")
        return error_msg, "text"


def update_chatroom_gptmodele(chatroom_name, chat_command, mdole_string, file_path=None):
    """
    채팅방의 gpt_model 값을 mdole_string으로 업데이트합니다.
    file_path가 지정되지 않으면 기본 경로를 사용합니다.
    지원하지 않는 모델이면 안내 메시지와 리스트를 반환합니다.
    """
    if file_path is None:
        file_path = json_data_manager.CHATROOM_FILE_PATH

    available_models = dataManager.GPT_MODEL_LIST
    if mdole_string not in available_models:
        if not available_models:
            return "모델 리스트를 불러올 수 없습니다. API Key 또는 네트워크를 확인해주세요.", "text"
        msg = (
            f"해당 모델은 지원하지 않습니다. 지원 가능한 리스트를 확인해주세요.\n"
            f"지원 가능한 모델:\n" + "\n".join(f"- {mid}" for mid in available_models)
        )
        return msg, "text"

    json_data_manager.update_chatroom_data(chatroom_name, "gpt_model", mdole_string, file_path)
    return f"모델이 '{mdole_string}'(으)로 변경되었습니다.", "text"

def chatroom_gpt_model(opentalk_name, chat_command, message):
    """
    현재 채팅방에서 사용 중인 GPT 모델을 조회하는 함수
    """
    current_model = json_data_manager.get_chatroom_data(opentalk_name, "gpt_model")
    if current_model:
        return f"현재 채팅방에서 사용 중인 GPT 모델: {current_model}", "text"
    else:
        return f"현재 채팅방의 GPT 모델 정보를 찾을 수 없습니다.", "text"

def api_usage_status(opentalk_name, chat_command, message):
    """
    API 사용량 현황을 조회하는 함수
    """
    return get_usage_summary(), "text"