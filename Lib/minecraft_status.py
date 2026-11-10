# -*- coding: utf-8 -*-
"""
#마크 — 마인크래프트 서버에 지금 접속해 있는 사람을 알려준다.

조회 방법은 두 가지를 함께 쓴다.
1) 서버 목록 핑(Server List Ping): 게임 클라이언트가 멀티플레이 목록에서 쓰는 것과 같은 요청.
   서버가 켜져 있는지, 몇 명인지, (서버가 숨기지 않으면) 접속자 이름까지 바로 알려준다.
2) 로그 읽기: 핑이 이름을 안 주는 서버를 위해 logs/latest.log의 접속/퇴장 기록으로 이름을 보완한다.
   서버 폴더가 이 PC에 있을 때만 가능하다.

대상 서버는 다음 순서로 정한다.
- config/api_key.json 에 MINECRAFT_SERVER 항목이 있으면 그 주소 ("주소:포트", 여러 개는 쉼표,
  "이름=주소:포트" 형식으로 이름 지정 가능). 서버가 다른 PC에 있으면 이걸 써야 한다.
- 없으면 DefaultSetting.ini [FeatherMonitor]의 server_paths — 각 폴더의 server.properties에서
  포트를 읽어 이 PC(127.0.0.1)로 조회한다.
- 둘 다 없으면 127.0.0.1:25565.
"""
import json
import os
import re
import socket
import struct
from pathlib import Path

from Lib import Helper

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 25565
PING_TIMEOUT_SEC = 3
MAX_STATUS_BYTES = 1024 * 1024   # 상태 응답 상한 (비정상 서버 방어)
MAX_LOG_BYTES = 8 * 1024 * 1024  # 로그는 뒤쪽 이만큼만 읽는다

_LOG_JOIN = re.compile(r"\]: (\w+) joined the game\s*$")
_LOG_LEAVE = re.compile(r"\]: (\w+) (?:left the game|lost connection)")
_LOG_START = re.compile(r"\]: Starting minecraft server")
_COLOR_CODE = re.compile(r"§.")


# ─── 서버 목록 핑 ────────────────────────────────────────────────────────

def _varint(value):
    value &= 0xFFFFFFFF
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _read_exact(sock, count):
    data = bytearray()
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise ConnectionError("서버가 응답 도중 연결을 끊었습니다")
        data.extend(chunk)
    return bytes(data)


def _read_varint(sock):
    value = 0
    for shift in range(0, 35, 7):
        byte = _read_exact(sock, 1)[0]
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value
    raise ValueError("잘못된 VarInt")


def ping(host, port, timeout=PING_TIMEOUT_SEC):
    """
    서버 상태(JSON → dict)를 돌려준다. 꺼져 있거나 응답이 없으면 OSError/ValueError.
    프로토콜: 핸드셰이크(다음 상태=1) → 상태 요청 → JSON 문자열 응답. (1.7 이상 공통)
    """
    host_bytes = host.encode("utf-8")
    handshake = (
        b"\x00"
        + _varint(-1)                       # 프로토콜 버전: 상태 조회는 -1 관례
        + _varint(len(host_bytes)) + host_bytes
        + struct.pack(">H", port)
        + _varint(1)                        # 다음 상태: status
    )
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(_varint(len(handshake)) + handshake)
        sock.sendall(b"\x01\x00")           # 길이 1, 패킷 ID 0 (상태 요청)

        _read_varint(sock)                  # 패킷 길이
        if _read_varint(sock) != 0:
            raise ValueError("예상하지 못한 패킷")
        length = _read_varint(sock)
        if not 0 < length <= MAX_STATUS_BYTES:
            raise ValueError("상태 응답 크기가 비정상입니다")
        status = json.loads(_read_exact(sock, length).decode("utf-8"))
    if not isinstance(status, dict):
        raise ValueError("상태 응답 형식이 올바르지 않습니다")
    return status


def players_from_status(status):
    """(접속 수, 최대 인원, 이름 목록). 이름 목록은 서버가 숨기면 비어 있다."""
    players = status.get("players")
    if not isinstance(players, dict):
        return 0, None, []
    try:
        online = int(players.get("online", 0))
    except (TypeError, ValueError):
        online = 0
    maximum = players.get("max")
    names = []
    for entry in players.get("sample") or []:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            name = _COLOR_CODE.sub("", entry["name"]).strip()
            if name and name not in names:
                names.append(name)
    return online, maximum, names


# ─── 로그 읽기 ───────────────────────────────────────────────────────────

def players_from_log_text(text):
    """마지막 서버 시작 이후의 접속/퇴장 기록으로 현재 접속자 이름 목록을 만든다."""
    online = []
    for line in text.splitlines():
        if _LOG_START.search(line):
            online = []
            continue
        match = _LOG_JOIN.search(line)
        if match:
            if match.group(1) not in online:
                online.append(match.group(1))
            continue
        match = _LOG_LEAVE.search(line)
        if match and match.group(1) in online:
            online.remove(match.group(1))
    return online


def players_from_log_file(log_path):
    """읽을 수 없으면 None."""
    try:
        with open(log_path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - MAX_LOG_BYTES))
            raw = handle.read()
    except OSError:
        return None
    return players_from_log_text(raw.decode("utf-8", errors="ignore"))


# ─── 대상 서버 ───────────────────────────────────────────────────────────

def _split_address(address):
    address = address.strip()
    if address.startswith("["):  # [IPv6]:port
        host, _, rest = address[1:].partition("]")
        port_text = rest.lstrip(":")
    elif address.count(":") == 1:
        host, port_text = address.split(":")
    else:
        host, port_text = address, ""
    try:
        port = int(port_text) if port_text else DEFAULT_PORT
    except ValueError:
        port = DEFAULT_PORT
    if not 0 < port < 65536:
        port = DEFAULT_PORT
    return host.strip() or DEFAULT_HOST, port


def _read_server_port(server_path):
    try:
        with open(Path(server_path) / "server.properties", "r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                key, _, value = line.partition("=")
                if key.strip() == "server-port":
                    port = int(value.strip())
                    if 0 < port < 65536:
                        return port
    except (OSError, ValueError):
        pass
    return DEFAULT_PORT


def _feather_servers():
    """[FeatherMonitor] 설정에서 (이름, 폴더, 로그 파일명) 목록을 읽는다."""
    try:
        from Lib import dataManager

        config = dataManager.DefaultSettingConfig
        paths_text = config.get("FeatherMonitor", "server_paths", fallback="") or ""
        names_text = config.get("FeatherMonitor", "server_names", fallback="") or ""
        log_filename = config.get("FeatherMonitor", "log_filename", fallback="latest.log") or "latest.log"
    except Exception as e:
        Helper.CustomPrint(f"⚠️ [마크] 서버 설정을 읽지 못했습니다: {e}")
        return []

    paths = [p.strip() for p in paths_text.split(",") if p.strip()]
    names = [n.strip() for n in names_text.split(",") if n.strip()]
    if len(names) != len(paths):
        names = [Path(p).name for p in paths]
    return [(name, path, log_filename) for name, path in zip(names, paths)]


def resolve_targets():
    """조회할 서버 목록: [{name, host, port, log_path}]"""
    targets = []
    override = os.environ.get("MINECRAFT_SERVER", "").strip()
    if override:
        for index, item in enumerate(p.strip() for p in override.split(",") if p.strip()):
            name, separator, address = item.partition("=")
            if not separator:
                name, address = "", item
            host, port = _split_address(address)
            targets.append({
                "name": name.strip() or ("마크서버" if index == 0 else f"마크서버{index + 1}"),
                "host": host, "port": port, "log_path": None,
            })
        return targets

    for name, path, log_filename in _feather_servers():
        targets.append({
            "name": name,
            "host": DEFAULT_HOST,
            "port": _read_server_port(path),
            "log_path": str(Path(path) / "logs" / log_filename),
        })
    if not targets:
        targets.append({"name": "마크서버", "host": DEFAULT_HOST, "port": DEFAULT_PORT, "log_path": None})
    return targets


# ─── 응답 만들기 ─────────────────────────────────────────────────────────

def describe_server(target):
    name = target["name"]
    try:
        status = ping(target["host"], target["port"])
    except (OSError, ValueError) as e:
        Helper.CustomPrint(
            f"ℹ️ [마크] {name} ({target['host']}:{target['port']}) 응답 없음: {type(e).__name__}: {e}"
        )
        return f"🔴 [{name}] 서버가 꺼져 있거나 응답이 없습니다."

    online, maximum, names = players_from_status(status)
    capacity = f"{online}/{maximum}명" if maximum is not None else f"{online}명"
    if online <= 0:
        return f"🟢 [{name}] 지금 접속 중인 사람이 없습니다. ({capacity})"

    if len(names) < online and target.get("log_path"):
        from_log = players_from_log_file(target["log_path"]) or []
        # 로그 쪽 인원이 핑과 맞을 때만 로그를 믿는다 (비정상 종료로 퇴장 기록이 빠질 수 있다)
        if len(from_log) == online:
            names = from_log

    lines = [f"🟢 [{name}] 접속 중 {capacity}"]
    lines.extend(f"- {player}" for player in names)
    if not names:
        lines.append("(서버가 접속자 이름을 공개하지 않습니다)")
    elif len(names) < online:
        lines.append(f"…외 {online - len(names)}명")
    return "\n".join(lines)


def GetData(opentalk_name, chat_command, message):
    """#마크 핸들러. 어떤 실패에서도 ("안내문", "text")를 반환한다."""
    try:
        return "\n\n".join(describe_server(target) for target in resolve_targets()), "text"
    except Exception as e:
        Helper.CustomPrint(f"❌ [마크] 미처리 예외 ({type(e).__name__}): {e}")
        return "마크 서버 상태를 확인하지 못했습니다.", "text"
