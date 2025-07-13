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
    answer = resp.choices[0].message.content
    if answer is not None:
        answer = answer.strip()
    else:
        answer = ""
    max_chars = GPT_MAX_TOKEN * 2  # 한글 기준 대략치
    show_limit_notice = len(answer) >= int(max_chars * 0.9)
    if show_limit_notice:
        text = f'질문하신 "{prompt}"에 대한 답변입니다. 최대 약 {max_chars}자까지 답변이 가능합니다.\n- {answer}'
    else:
        text = f'질문하신 "{prompt}"에 대한 답변입니다.\n- {answer}'
    return text, "text"

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