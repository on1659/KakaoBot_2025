import os
import time
import re
import threading
from pathlib import Path
from datetime import datetime
from Lib import Helper

class FeatherLogMonitor:
    def __init__(self, server_paths, notification_room_name, server_names=None):
        """
        Feather Launcher 마크서버 로그 모니터링 클래스
        
        Args:
            server_paths (list): 서버 로그 경로 리스트
            notification_room_name (str): 알림을 보낼 카카오톡 방 이름
            server_names (list): 서버 이름 리스트 (선택사항, 없으면 폴더명 사용)
        """
        self.server_paths = server_paths
        self.notification_room_name = notification_room_name
        self.monitoring = False
        self.monitor_thread = None
        self.last_positions = {}
        self.start_time = None  # 모니터링 시작 시간
        
        # 서버 경로와 이름 매핑
        self.server_name_map = {}
        if server_names and len(server_names) == len(server_paths):
            for path, name in zip(server_paths, server_names):
                self.server_name_map[path] = name
        else:
            # 서버 이름이 없거나 개수가 맞지 않으면 폴더명 사용
            for path in server_paths:
                self.server_name_map[path] = Path(path).name
        
        # 활성 서버 목록 (서버 종료 시 제거됨)
        self.active_servers = set(server_paths)
        
        # 접속 감지 패턴들
        self.join_patterns = [
            r'\[.*?\] \[Server thread/INFO\]: (\w+) joined the game',
            r'\[.*?\] \[Server thread/INFO\]: (\w+) logged in',
            r'\[.*?\] \[Server thread/INFO\]: (\w+) connected',
            r'\[.*?\] \[Server thread/INFO\]: (\w+) 접속',
            r'\[.*?\] \[Server thread/INFO\]: (\w+) 로그인'
        ]
        
        # 퇴장 감지 패턴들
        self.leave_patterns = [
            # 정상 퇴장
            # 정상 퇴장
            r'\[.*?\] \[Server thread/INFO\]: (\w+) left the game',
            r'\[.*?\] \[Server thread/INFO\]: (\w+) logged out',
            r'\[.*?\] \[Server thread/INFO\]: (\w+) has left the server',
            r'\[.*?\] \[Server thread/INFO\]: (\w+) 퇴장',
            
            # 연결 문제 (더 정확한 패턴)
            r'\[.*?\] \[Server thread/INFO\]: (\w+) disconnected',
            r'\[.*?\] \[Server thread/INFO\]: (\w+) lost connection.*?',
            r'\[.*?\] \[Server thread/INFO\]: (\w+).*?Read timed out',
            r'\[.*?\] \[Server thread/INFO\]: (\w+).*?timed out',
            r'\[.*?\] \[Server thread/INFO\]: (\w+).*?Connection timeout',
            r'\[.*?\] \[Server thread/INFO\]: (\w+).*?Connection reset',
            r'\[.*?\] \[Server thread/INFO\]: (\w+).*?Connection reset by peer',
            r'\[.*?\] \[Server thread/INFO\]: (\w+).*?Broken pipe',
            
            # 킥 관련
            r'\[.*?\] \[Server thread/INFO\]: (\w+) was kicked',
            r'\[.*?\] \[Server thread/INFO\]: (\w+) has been kicked',
            r'\[.*?\] \[Server thread/INFO\]: Kicked (\w+)',
            
            # 서버 측 이슈
            r'\[.*?\] \[Server thread/INFO\]: (\w+).*?Internal Exception',
            r'\[.*?\] \[Server thread/INFO\]: (\w+).*?IOException',
            r'\[.*?\] \[Server thread/ERROR\]: (\w+).*?Exception',
            
            # UUID 관련 (UUID 메시지도 퇴장의 일종) - 다양한 스레드에서 발생 가능
            r'\[.*?\] \[.*?/INFO\]: UUID of player (\w+) is'
        ]
        
        # 서버 종료 감지 패턴들
        self.server_stop_patterns = [
            r'\[.*?\] \[Server thread/INFO\]: Stopping the server',
            r'\[.*?\] \[Server thread/INFO\]: Goodbye',
            r'\[.*?\] \[Server thread/INFO\]: ThreadedAnvilChunkStorage: All dimensions are saved'
        ]
        
        # 서버 크래시 감지 패턴들
        self.server_crash_patterns = [
            r'java\.lang\.RuntimeException: Server crash!',
            r'Server crash!',
            r'\[.*?\] \[Server thread/ERROR\]: This crash report has been saved to',
            r'\[.*?\] \[Server thread/ERROR\]: Encountered an unexpected exception'
        ]
        
        Helper.CustomPrint(f"🔍 Feather 로그 모니터링 초기화 완료")
        Helper.CustomPrint(f"📁 모니터링 서버: {len(server_paths)}개")
        Helper.CustomPrint(f"💬 알림 방: {notification_room_name}")
    
    def start_monitoring(self):
        """로그 모니터링 시작"""
        if self.monitoring:
            Helper.CustomPrint("⚠️ 이미 모니터링 중입니다.")
            return
        
        self.monitoring = True
        self.start_time = datetime.now()  # 모니터링 시작 시간 기록
        
        # 활성 서버 목록 초기화 (모든 서버가 다시 활성 상태로)
        self.active_servers = set(self.server_paths)
        
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        Helper.CustomPrint("✅ Feather 로그 모니터링 시작")
    
    def stop_monitoring(self):
        """로그 모니터링 중지"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)
        Helper.CustomPrint("⏹️ Feather 로그 모니터링 중지")
    
    def _monitor_loop(self):
        """모니터링 메인 루프"""
        while self.monitoring:
            try:
                # 활성 서버만 체크
                active_servers_copy = self.active_servers.copy()  # 반복 중 수정 방지
                for server_path in active_servers_copy:
                    self._check_server_log(server_path)
                
                # 모든 서버가 종료되었으면 모니터링 중지
                if not self.active_servers:
                    Helper.CustomPrint("🔴 모든 서버가 종료되어 모니터링을 중지합니다.")
                    self._send_kakao_message("🔴 모든 서버가 종료되어 로그 모니터링이 자동 중지되었습니다.")
                    self.monitoring = False
                    break
                
                time.sleep(1)  # 1초마다 체크
            except Exception as e:
                Helper.CustomPrint(f"❌ 로그 모니터링 오류: {str(e)}")
                time.sleep(5)  # 오류 시 5초 대기
    
    def _check_server_log(self, server_path):
        """개별 서버 로그 체크"""
        # 비활성 서버는 체크하지 않음
        if server_path not in self.active_servers:
            return
            
        log_file = Path(server_path) / "logs" / "latest.log"
        
        if not log_file.exists():
            return
        
        try:
            # 파일 크기 확인
            current_size = log_file.stat().st_size
            last_position = self.last_positions.get(str(log_file), 0)
            
            # 파일이 새로 생성되었거나 크기가 줄어든 경우 (로그 로테이션)
            if current_size < last_position:
                last_position = 0
            
            # 새로운 내용이 있는 경우
            if current_size > last_position:
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(last_position)
                    new_lines = f.readlines()
                    
                    for line in new_lines:
                        self._process_log_line(line.strip(), server_path)
                
                self.last_positions[str(log_file)] = current_size
                
        except Exception as e:
            Helper.CustomPrint(f"❌ 로그 파일 읽기 오류 ({server_path}): {str(e)}")
    
    def _process_log_line(self, line, server_path):
        """로그 라인 처리"""
        if not line:
            return
        
        # 로그 라인의 타임스탬프 추출 및 모니터링 시작 시간과 비교
        if not self._is_log_after_start_time(line):
            return  # 모니터링 시작 이전의 로그는 무시
        
        # 접속 감지
        for pattern in self.join_patterns:
            match = re.search(pattern, line)
            if match:
                player_name = match.group(1)
                server_name = self.server_name_map[server_path]
                message = f"🎮 [{server_name}] {player_name}님이 로그인하셨습니다."
                
                Helper.CustomPrint(f"🎮 {player_name}님이 {server_name} 서버에 접속했습니다!")
                self._send_kakao_message(message)
                return
        
        # 퇴장 감지
        for pattern in self.leave_patterns:
            match = re.search(pattern, line)
            if match:
                player_name = match.group(1)
                server_name = self.server_name_map[server_path]
                message = f"🚪 [{server_name}] {player_name}님이 로그아웃하셨습니다."
                
                Helper.CustomPrint(f"🚪 {player_name}님이 {server_name} 서버에서 퇴장했습니다.")
                self._send_kakao_message(message)
                return
        
        # 서버 종료 감지
        for pattern in self.server_stop_patterns:
            if re.search(pattern, line):
                server_name = self.server_name_map[server_path]
                message = f"🔴 [{server_name}] 서버가 종료되었습니다."
                
                Helper.CustomPrint(f"🔴 {server_name} 서버가 종료되었습니다!")
                self._send_kakao_message(message)
                
                # 해당 서버를 활성 목록에서 제거
                if server_path in self.active_servers:
                    self.active_servers.remove(server_path)
                    Helper.CustomPrint(f"📤 {server_name} 서버 모니터링을 중지합니다.")
                    
                    # 남은 활성 서버 개수 확인
                    if self.active_servers:
                        remaining_servers = [self.server_name_map[path] for path in self.active_servers]
                        Helper.CustomPrint(f"📋 남은 활성 서버: {', '.join(remaining_servers)}")
                    else:
                        Helper.CustomPrint("📋 모든 서버가 종료되었습니다.")
                
                return
        
        # 서버 크래시 감지
        for pattern in self.server_crash_patterns:
            if re.search(pattern, line):
                server_name = self.server_name_map[server_path]
                message = f"💥 [{server_name}] 서버에서 크래시가 발생했습니다!"
                
                Helper.CustomPrint(f"💥 {server_name} 서버에서 크래시가 발생했습니다!")
                self._send_kakao_message(message)
                
                # 해당 서버를 활성 목록에서 제거 (크래시도 서버 종료)
                if server_path in self.active_servers:
                    self.active_servers.remove(server_path)
                    Helper.CustomPrint(f"📤 {server_name} 서버 모니터링을 중지합니다. (크래시)")
                    
                    # 남은 활성 서버 개수 확인
                    if self.active_servers:
                        remaining_servers = [self.server_name_map[path] for path in self.active_servers]
                        Helper.CustomPrint(f"📋 남은 활성 서버: {', '.join(remaining_servers)}")
                    else:
                        Helper.CustomPrint("📋 모든 서버가 종료되었습니다.")
                
                return
    
    def _is_log_after_start_time(self, log_line):
        """로그 라인이 모니터링 시작 시간 이후인지 확인"""
        if not self.start_time:
            return True
        
        # 로그 라인에서 타임스탬프 추출 (예: [12:34:56])
        timestamp_match = re.search(r'\[(\d{2}:\d{2}:\d{2})\]', log_line)
        if not timestamp_match:
            return True  # 타임스탬프가 없으면 처리
        
        try:
            log_time_str = timestamp_match.group(1)
            log_time = datetime.strptime(log_time_str, "%H:%M:%S").time()
            start_time = self.start_time.time()
            
            # 같은 날의 시간 비교
            return log_time >= start_time
        except:
            return True  # 파싱 오류 시 처리
    def _send_kakao_message(self, message):
        """카카오톡 메시지를 큐에 추가"""
        if not global_chat_list:
            Helper.CustomPrint(f"⏳ chatList가 아직 초기화되지 않았습니다.")
            return
            
        for chat in global_chat_list:
            if chat.chatroom_name == self.notification_room_name:
                chat.add_message_to_queue(message, "text")
                return
        
        Helper.CustomPrint(f"⚠️ 알림 방을 찾을 수 없습니다: {self.notification_room_name}")

# 전역 변수들
feather_monitor = None
global_chat_list = None

def set_global_chat_list(chat_list):
    """전역 chatList 설정"""
    global global_chat_list
    global_chat_list = chat_list

def start_feather_monitoring(server_paths, notification_room_name, server_names=None):
    """Feather 로그 모니터링 시작"""
    global feather_monitor
    
    if feather_monitor:
        feather_monitor.stop_monitoring()
    
    feather_monitor = FeatherLogMonitor(server_paths, notification_room_name, server_names)
    feather_monitor.start_monitoring()
    return feather_monitor

def start_feather_monitoring_from_config():
    """설정 파일에서 Feather 모니터링 정보를 읽어 모니터링 시작"""
    try:
        from Lib import dataManager
        
        # 설정에서 Feather 모니터링 정보 읽기
        enabled = dataManager.DefaultSettingConfig.getboolean('FeatherMonitor', 'enabled', fallback=False)
        if not enabled:
            Helper.CustomPrint("ℹ️ Feather 모니터링이 비활성화되어 있습니다.")
            return None
        
        notification_room = dataManager.DefaultSettingConfig.get('FeatherMonitor', 'notification_room', fallback='이더')
        server_paths_str = dataManager.DefaultSettingConfig.get('FeatherMonitor', 'server_paths', fallback='')
        server_names_str = dataManager.DefaultSettingConfig.get('FeatherMonitor', 'server_names', fallback='')
        
        if not server_paths_str:
            Helper.CustomPrint("⚠️ Feather 서버 경로가 설정되지 않았습니다.")
            return None
        
        server_paths = [path.strip() for path in server_paths_str.split(',')]
        server_names = None
        
        # 서버 이름이 설정되어 있으면 사용
        if server_names_str:
            server_names = [name.strip() for name in server_names_str.split(',')]
            if len(server_names) != len(server_paths):
                Helper.CustomPrint("⚠️ 서버 경로와 서버 이름의 개수가 맞지 않습니다. 폴더명을 사용합니다.")
                server_names = None
        
        Helper.CustomPrint(f"🎮 Feather 모니터링 설정:")
        Helper.CustomPrint(f"   📁 서버 경로: {len(server_paths)}개")
        Helper.CustomPrint(f"   🏷️ 서버 이름: {'사용자 정의' if server_names else '폴더명 사용'}")
        Helper.CustomPrint(f"   💬 알림 방: {notification_room}")
        
        # 모니터링 시작
        monitor = start_feather_monitoring(server_paths, notification_room, server_names)
        return monitor
        
    except Exception as e:
        Helper.CustomPrint(f"❌ Feather 모니터링 시작 실패: {str(e)}")
        return None

def stop_feather_monitoring():
    """Feather 로그 모니터링 중지"""
    global feather_monitor
    
    if feather_monitor:
        feather_monitor.stop_monitoring()
        feather_monitor = None

def start_feather_monitoring_command(chatroom_name, chat_command, message):
    """#마크노티시작 명령어 처리"""
    global feather_monitor
    
    if feather_monitor and feather_monitor.monitoring:
        return "⚠️ 이미 Feather 로그 모니터링이 실행 중입니다.", "text"
    
    # 설정에서 모니터링 시작
    monitor = start_feather_monitoring_from_config()
    if monitor:
        return "✅ Feather 로그 모니터링이 시작되었습니다! 🎮", "text"
    else:
        return "❌ Feather 로그 모니터링 시작에 실패했습니다. 설정을 확인해주세요.", "text"

def stop_feather_monitoring_command(chatroom_name, chat_command, message):
    """#마크노티종료 명령어 처리"""
    global feather_monitor
    
    if not feather_monitor or not feather_monitor.monitoring:
        return "⚠️ 현재 Feather 로그 모니터링이 실행되고 있지 않습니다.", "text"
    
    stop_feather_monitoring()
    return "⏹️ Feather 로그 모니터링이 중지되었습니다.", "text"

def check_feather_monitoring_status(chatroom_name, chat_command, message):
    """#마크노티상태 명령어 처리"""
    global feather_monitor
    
    if feather_monitor and feather_monitor.monitoring:
        total_server_count = len(feather_monitor.server_paths)
        active_server_count = len(feather_monitor.active_servers)
        notification_room = feather_monitor.notification_room_name
        
        # 활성 서버 이름 목록
        active_server_names = [feather_monitor.server_name_map[path] for path in feather_monitor.active_servers]
        
        status_msg = f"🎮 Feather 로그 모니터링 상태: 실행 중\n"
        status_msg += f"📁 전체 서버: {total_server_count}개\n"
        status_msg += f"🟢 활성 서버: {active_server_count}개\n"
        if active_server_names:
            status_msg += f"📋 활성 서버 목록: {', '.join(active_server_names)}\n"
        status_msg += f"💬 알림 방: {notification_room}\n"
        status_msg += f"📋 감지 이벤트:\n"
        status_msg += f"  🟢 플레이어 접속/퇴장\n"
        status_msg += f"  🔴 서버 종료 (자동 모니터링 중지)\n"
        status_msg += f"  💥 서버 크래시 (자동 모니터링 중지)"
        return status_msg, "text"
    else:
        return "⏹️ Feather 로그 모니터링 상태: 중지됨", "text" 