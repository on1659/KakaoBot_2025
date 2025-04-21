
from datetime import datetime

def CustomPrint(messages, saveLog = 1):
    full_message = "".join(str(m) for m in messages)
    ts = datetime.now().strftime("%m-%d-%H:%M:%S")
    print(f"{ts} // {full_message}")
