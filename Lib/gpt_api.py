# 파일명: gpt_api.py
import os
import openai
from . import json_data_manager

openai.api_key = os.environ.get("OPENAI_API_KEY")  # 또는 직접 문자열로 할당


def getData(opentalk_name, cheate_commnad, user_prompt):
    model = json_data_manager.get_chatroom_data(opentalk_name, "gpt_model")
    return ask_gpt(user_prompt, model)


# 2) GPT 호출 함수
def ask_gpt(prompt, model):
    response = openai.ChatCompletion.create(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=100
    )
    # 첫 번째 응답 메시지
    return response.choices[0].message.content
