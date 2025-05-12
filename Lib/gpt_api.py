import os
import openai

from . import json_data_manager  # 같은 패키지 내 모듈로 가정
from . import dataManager  # 같은 패키지 내 모듈로 가정

# 1) OpenAI API Key 설정
openai.api_key = os.environ.get("OPENAI_API_KEY")
GPT_MAX_TOKEN = int(dataManager.GPT_MAX_TOKEN)

def getData(opentalk_name: str, chat_command: str, user_prompt: str):
    """
    채팅방 이름(opentalk_name)과 명령어(chat_command), 사용자 프롬프트(user_prompt)를 받아
    DB/JSON에서 GPT 모델을 조회한 후 ask_gpt 함수를 호출하여 (응답, 메시지타입)을 반환.
    """
    # JSON에서 꺼낸 모델 이름이 None 이면 기본값 사용
    model_name = json_data_manager.get_chatroom_data(opentalk_name, "gpt_model") or "gpt-3.5-turbo"
    return ask_gpt(user_prompt, model_name)

def ask_gpt(prompt: str, model_name: str = "gpt-3.5-turbo"):
    """
    사용자 프롬프트(prompt)와 모델 이름(model_name)을 받아,
    OpenAI Chat API를 호출 후 (응답문자열, "text") 를 반환.
    """
    # prompt = f"{prompt}\n\n답변은 반드시 {GPT_MAX_TOKEN} 토큰보다 짧게 해줘."
    resp = openai.chat.completions.create(
        model = model_name,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user",   "content": prompt}
        ],
        temperature=0.7,
        max_tokens = GPT_MAX_TOKEN,
    )
    # openai>=1.0.0 에서는 resp.choices[0].message.content
    answer = resp.choices[0].message.content.strip()
    max_chars = GPT_MAX_TOKEN * 2  # 한글 기준 대략치
    show_limit_notice = len(answer) >= int(max_chars * 0.9)
    if show_limit_notice:
        text = f'질문하신 "{prompt}"에 대한 답변입니다. 최대 약 {max_chars}자까지 답변이 가능합니다.\n- {answer}'
    else:
        text = f'질문하신 "{prompt}"에 대한 답변입니다.\n- {answer}'
    return text, "text"

# 단독 실행 시 간단 테스트
if __name__ == "__main__":
    room = "test_room"
    cmd  = "#gpt"
    user_prompt = "파리의 수도는 어디인가요?"
    reply, msg_type = getData(room, cmd, user_prompt)
    print(f"[{msg_type}] {reply}")