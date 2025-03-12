# 파일명: gpt_api.py
import os
import openai
from . import json_data_manager  # 같은 패키지 내 모듈로 가정

# 1) OpenAI API Key 설정
openai.api_key = os.environ.get("OPENAI_API_KEY")

def getData(opentalk_name, chat_command, user_prompt):
    """
    채팅방 이름(opentalk_name)과 명령어(chat_command), 사용자 프롬프트(user_prompt)를 받아
    DB/JSON에서 GPT 모델을 조회한 후 ask_gpt 함수를 호출하여 응답을 반환.
    """
    # 예: JSON 파일에서 "gpt_model"이라는 키로 모델명을 가져온다고 가정
    model_name = json_data_manager.get_chatroom_data(opentalk_name, "gpt_model")

    # ask_gpt 호출 (모델명이 None이면 기본 모델 "gpt-3.5-turbo" 사용)
    return ask_gpt(user_prompt, model_name)

def ask_gpt(prompt, model_name=None):
    """
    사용자 프롬프트(prompt)와 모델 이름(model_name)을 받아,
    OpenAI ChatCompletion API를 호출 후 응답 문자열을 반환.
    """
    # 만약 model_name이 None이면 기본 모델(gpt-3.5-turbo) 사용
    if not model_name:
        model_name = "gpt-3.5-turbo"

    response = openai.ChatCompletion.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=100
    )
    # 첫 번째 응답 메시지 추출
    return response.choices[0].message.content
