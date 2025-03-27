
from Lib import youtube, convert_naver_map, every_mention, json_data_manager
from Lib import gpt_api, insta


# # 카톡창 이름, (활성화 상태의 열려있는 창)
kakao_opentalk_name_List = [
    '테스트방이야'
    ,'이더'
    ,'하트시그널 토론회장'
  # , '김자기💖'
]

chat_command_Map = [
    ['#유툽', youtube.GetData],
    ['[카카오맵]', convert_naver_map.GetData],
    ['#all', every_mention.GetData],
    ['#방인원',json_data_manager.save_chatroom_info],
    ['#gpt', gpt_api.getData],
    ['https://www.instagram.com/', insta.GetData]
    ]
