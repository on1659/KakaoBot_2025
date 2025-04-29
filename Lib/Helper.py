import sys, os
from datetime import datetime

IS_DEBUG_MODE = 'pydevd' in sys.modules

def CustomPrint(messages, saveLog = 0):
    full_message = "".join(str(m) for m in messages)
    ts = datetime.now().strftime("%m-%d-%H:%M:%S")
    print(f"{ts} // {full_message}")

def is_debug_mode() -> bool:
    # PyCharm(또는 다른 IDE) 디버거가 붙어 있을 때만 True
    return (IS_DEBUG_MODE == 1)
def CheckMode():
    if is_debug_mode():
        CustomPrint("🐞 DEBUG 모드입니다.")
    else:
        CustomPrint("🔖 RELEASE 모드입니다.")