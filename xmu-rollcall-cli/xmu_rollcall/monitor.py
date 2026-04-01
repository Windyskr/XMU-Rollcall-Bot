import time
import os
import sys
import requests
import shutil
import re
from datetime import datetime, timedelta
from xmulogin import xmulogin
from .utils import clear_screen, save_session, load_session, verify_session
from .rollcall_handler import process_rollcalls
from .notification import send_bark_message
from .config import get_cookies_path, load_config, normalize_monitor_schedule

base_url = "https://lnt.xmu.edu.cn"
interval = 1

def _load_monitor_interval():
    """从配置文件加载监控间隔"""
    try:
        config = load_config()
        val = config.get("monitor_interval", 1)
        return max(1, int(val))
    except Exception:
        return 1


def _load_monitor_schedule():
    """从配置文件加载监控时段。"""
    try:
        config = load_config()
        return normalize_monitor_schedule(config.get("monitor_schedule"))
    except Exception:
        return normalize_monitor_schedule(None)

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://ids.xmu.edu.cn/authserver/login",
}

# ANSI Color codes
class Colors:
    __slots__ = ()
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    GRAY = '\033[90m'
    WHITE = '\033[97m'
    BG_BLUE = '\033[44m'
    BG_GREEN = '\033[42m'
    BG_CYAN = '\033[46m'

BOLD_LABEL = f"{Colors.BOLD}"
CYAN_TEXT = f"{Colors.OKCYAN}"
GREEN_TEXT = f"{Colors.OKGREEN}"
YELLOW_TEXT = f"{Colors.WARNING}"
END = Colors.ENDC

def get_terminal_width():
    """获取终端宽度"""
    try:
        return shutil.get_terminal_size().columns
    except:
        return 80

_ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def strip_ansi(text):
    """移除ANSI颜色代码以计算实际文本长度"""
    return _ANSI_ESCAPE.sub('', text)

def center_text(text, width=None):
    """居中文本"""
    if width is None:
        width = get_terminal_width()
    text_len = len(strip_ansi(text))
    if text_len >= width:
        return text
    left_padding = (width - text_len) // 2
    return ' ' * left_padding + text

def print_banner():
    """打印美化的横幅"""
    width = get_terminal_width()
    line = '=' * width

    title1 = "XMU Rollcall Bot CLI"
    title2 = "Version 3.3.0"

    print(f"{Colors.OKCYAN}{line}{Colors.ENDC}")
    print(center_text(f"{Colors.BOLD}{title1}{Colors.ENDC}"))
    print(center_text(f"{Colors.GRAY}{title2}{Colors.ENDC}"))
    print(f"{Colors.OKCYAN}{line}{Colors.ENDC}")

def print_separator(char="-"):
    """打印分隔线"""
    width = get_terminal_width()
    print(f"{Colors.GRAY}{char * width}{Colors.ENDC}")

def format_time(seconds):
    """格式化时间显示"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"

_COLOR_PALETTE = (
    Colors.FAIL,
    Colors.WARNING,
    Colors.OKGREEN,
    Colors.OKCYAN,
    Colors.OKBLUE,
    Colors.HEADER
)
_COLOR_COUNT = len(_COLOR_PALETTE)

def get_colorful_text(text, color_offset=0):
    """为文本的每个字符应用不同的颜色"""
    return ''.join(
        _COLOR_PALETTE[(i + color_offset) % _COLOR_COUNT] + char
        for i, char in enumerate(text)
    ) + Colors.ENDC

def print_footer_text(color_offset=0):
    """打印底部彩色文字"""
    text = "XMU-Rollcall-Bot @ KrsMt"
    colored = get_colorful_text(text, color_offset)
    print(center_text(colored))

def print_dashboard(
    name,
    start_time,
    query_count,
    banner_frame=0,
    show_banner=True,
    rollcall_state=None,
    monitor_state=None,
):
    """打印主仪表板"""
    clear_screen()
    print_banner()

    local_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

    if time.localtime().tm_hour < 12 and time.localtime().tm_hour >= 5:
        greeting = "Good morning"
    elif time.localtime().tm_hour < 18 and time.localtime().tm_hour >= 12:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    now = time.time()
    running_time = int(now - start_time)

    print(f"\n{Colors.OKGREEN}{Colors.BOLD}{greeting}, {name}!{Colors.ENDC}\n")

    print(f"{Colors.BOLD}SYSTEM STATUS{Colors.ENDC}")
    print_separator()
    print(f"{Colors.BOLD}Current Time:{Colors.ENDC}    {Colors.OKCYAN}{local_time}{Colors.ENDC}")
    print(f"{Colors.BOLD}Running Time:{Colors.ENDC}    {Colors.OKGREEN}{format_time(running_time)}{Colors.ENDC}")
    print(f"{Colors.BOLD}Query Count:{Colors.ENDC}     {Colors.WARNING}{query_count}{Colors.ENDC}")

    print(f"\n{Colors.BOLD}ROLLCALL MONITOR{Colors.ENDC}")
    print_separator()
    monitor_status = "Active - Monitoring for new rollcalls..."
    monitor_color = Colors.OKGREEN
    schedule_text = "Disabled (always on)"
    if monitor_state:
        monitor_status = monitor_state.get("status_text", monitor_status)
        monitor_color = monitor_state.get("status_color", monitor_color)
        schedule_text = monitor_state.get("schedule_text", schedule_text)
    print(f"{Colors.BOLD}Status:{Colors.ENDC}          {monitor_color}{monitor_status}{Colors.ENDC}")
    print(f"{Colors.BOLD}Schedule:{Colors.ENDC}        {Colors.OKCYAN}{schedule_text}{Colors.ENDC}")
    print(f"{Colors.GRAY}Checking every {interval} second(s) | Press Ctrl+C to exit{Colors.ENDC}\n")
    print(f"{Colors.BOLD}ACTIVE ROLLCALL{Colors.ENDC}")
    print_separator()
    active_rollcall = "None"
    sign_status = "Monitoring for new rollcalls"
    status_color = Colors.GRAY
    if rollcall_state:
        active_rollcall = rollcall_state.get("active_rollcall", active_rollcall)
        sign_status = rollcall_state.get("sign_status", sign_status)
        status_color = rollcall_state.get("status_color", status_color)
    print(f"{Colors.BOLD}Active Rollcall:{Colors.ENDC} {Colors.OKCYAN}{active_rollcall}{Colors.ENDC}")
    print(f"{Colors.BOLD}Sign Status:{Colors.ENDC}    {status_color}{sign_status}{Colors.ENDC}")
    print()
    print_separator()

    if show_banner:
        print()
        print_footer_text(banner_frame)

def print_login_status(message, is_success=True):
    """打印登录状态"""
    if is_success:
        print(f"{Colors.OKGREEN}[SUCCESS]{Colors.ENDC} {message}")
    else:
        print(f"{Colors.FAIL}[FAILED]{Colors.ENDC} {message}")


WEEKDAY_LABELS = {
    1: "Mon",
    2: "Tue",
    3: "Wed",
    4: "Thu",
    5: "Fri",
    6: "Sat",
    7: "Sun",
}


def _parse_schedule_time(time_text):
    """将 HH:MM 解析为小时和分钟。"""
    hour_text, minute_text = time_text.split(":")
    return int(hour_text), int(minute_text)


def _time_minutes(time_text):
    hour, minute = _parse_schedule_time(time_text)
    return hour * 60 + minute


def describe_schedule(schedule):
    """生成监控时段的人类可读描述。"""
    schedule = normalize_monitor_schedule(schedule)
    if not schedule.get("enabled"):
        return "Disabled (always on)"

    days = schedule.get("days", [])
    if days == [1, 2, 3, 4, 5, 6, 7]:
        days_text = "Every day"
    else:
        days_text = ", ".join(WEEKDAY_LABELS.get(day, str(day)) for day in days)
    return f"{days_text} {schedule.get('start_time')} - {schedule.get('end_time')}"


def is_in_schedule_window(schedule, now=None):
    """判断当前时间是否处于允许监控的时段。"""
    schedule = normalize_monitor_schedule(schedule)
    if not schedule.get("enabled"):
        return True

    now = now or datetime.now()
    current_minutes = now.hour * 60 + now.minute
    start_minutes = _time_minutes(schedule["start_time"])
    end_minutes = _time_minutes(schedule["end_time"])
    today = now.isoweekday()
    yesterday = 7 if today == 1 else today - 1
    days = set(schedule.get("days", []))

    if start_minutes == end_minutes:
        return today in days

    if start_minutes < end_minutes:
        return today in days and start_minutes <= current_minutes < end_minutes

    return (
        (today in days and current_minutes >= start_minutes)
        or (yesterday in days and current_minutes < end_minutes)
    )


def get_next_schedule_start(schedule, now=None):
    """获取下一个监控开始时间。"""
    schedule = normalize_monitor_schedule(schedule)
    if not schedule.get("enabled"):
        return None

    now = now or datetime.now()
    start_hour, start_minute = _parse_schedule_time(schedule["start_time"])
    days = set(schedule.get("days", []))

    for offset in range(0, 15):
        candidate_date = now.date() + timedelta(days=offset)
        if candidate_date.isoweekday() not in days:
            continue
        candidate = datetime.combine(
            candidate_date,
            datetime.min.time(),
        ).replace(hour=start_hour, minute=start_minute)
        if candidate > now:
            return candidate
    return None


def get_current_window_end(schedule, now=None):
    """获取当前这段监控窗口的结束时间。"""
    schedule = normalize_monitor_schedule(schedule)
    if not schedule.get("enabled"):
        return None

    now = now or datetime.now()
    if not is_in_schedule_window(schedule, now):
        return None

    start_minutes = _time_minutes(schedule["start_time"])
    end_minutes = _time_minutes(schedule["end_time"])
    end_hour, end_minute = _parse_schedule_time(schedule["end_time"])
    today_start = datetime.combine(now.date(), datetime.min.time())

    if start_minutes == end_minutes:
        return today_start + timedelta(days=1, hours=end_hour, minutes=end_minute)

    if start_minutes < end_minutes:
        return today_start.replace(hour=end_hour, minute=end_minute)

    current_minutes = now.hour * 60 + now.minute
    if current_minutes >= start_minutes:
        return today_start + timedelta(days=1, hours=end_hour, minutes=end_minute)
    return today_start.replace(hour=end_hour, minute=end_minute)

TIME_LINE = 10
RUNTIME_LINE = 11
QUERY_LINE = 12
MONITOR_STATUS_LINE = 16
SCHEDULE_LINE = 17
ACTIVE_ROLLCALL_LINE = 22
SIGN_STATUS_LINE = 23
FOOTER_LINE = 26

def update_status_line(line_num, label, value, color):
    """更新指定行的状态信息，不清屏"""
    sys.stdout.write("\033[?25l")
    sys.stdout.write("\033[s")
    sys.stdout.write(f"\033[{line_num};0H")
    sys.stdout.write("\033[2K")
    sys.stdout.write(f"{Colors.BOLD}{label}{Colors.ENDC}    {color}{value}{Colors.ENDC}")
    sys.stdout.write("\033[u")
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()

def update_footer_text():
    """更新底部彩色文字，不清屏"""
    text = "XMU-Rollcall-Bot @ KrsMt"
    colored = get_colorful_text(text, 0)
    width = get_terminal_width()

    sys.stdout.write("\033[?25l")
    sys.stdout.write("\033[s")
    sys.stdout.write(f"\033[{FOOTER_LINE};0H")
    sys.stdout.write("\033[2K")

    text_len = len(text)
    left_padding = (width - text_len) // 2
    sys.stdout.write(' ' * left_padding + colored)

    sys.stdout.write("\033[u")
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


def get_rollcall_status_color(status_type):
    if status_type == "working":
        return Colors.WARNING
    if status_type == "success":
        return Colors.OKGREEN
    if status_type == "failure":
        return Colors.FAIL
    if status_type == "pending":
        return Colors.OKCYAN
    return Colors.GRAY


def update_rollcall_status_lines(rollcall_state):
    update_status_line(
        ACTIVE_ROLLCALL_LINE,
        "Active Rollcall:",
        rollcall_state.get("active_rollcall", "None"),
        Colors.OKCYAN,
    )
    update_status_line(
        SIGN_STATUS_LINE,
        "Sign Status:",
        rollcall_state.get("sign_status", "Monitoring for new rollcalls"),
        rollcall_state.get("status_color", Colors.GRAY),
    )


def update_monitor_status_lines(monitor_state):
    update_status_line(
        MONITOR_STATUS_LINE,
        "Status:",
        monitor_state.get("status_text", "Active - Monitoring for new rollcalls..."),
        monitor_state.get("status_color", Colors.OKGREEN),
    )
    update_status_line(
        SCHEDULE_LINE,
        "Schedule:",
        monitor_state.get("schedule_text", "Disabled (always on)"),
        Colors.OKCYAN,
    )

def start_monitor(account):
    """启动监控程序"""
    global interval
    interval = _load_monitor_interval()
    monitor_schedule = _load_monitor_schedule()
    schedule_description = describe_schedule(monitor_schedule)

    USERNAME = account['username']
    PASSWORD = account['password']
    ACCOUNT_ID = account.get('id', 1)
    ACCOUNT_NAME = account.get('name', '')
    # LATITUDE = account.get('latitude', 0)
    # LONGITUDE = account.get('longitude', 0)

    # 设置全局位置信息
    # set_location(LATITUDE, LONGITUDE)

    cookies_path = get_cookies_path(ACCOUNT_ID)
    rollcalls_url = f"{base_url}/api/radar/rollcalls"
    session = None

    # 初始化
    clear_screen()
    print_banner()
    print(f"\n{Colors.BOLD}Initializing XMU Rollcall Bot...{Colors.ENDC}\n")
    print_separator()

    print(f"\n{Colors.OKCYAN}[Step 1/3]{Colors.ENDC} Checking credentials...")

    if os.path.exists(cookies_path):
        print(f"{Colors.OKCYAN}[Step 2/3]{Colors.ENDC} Found cached session, attempting to restore...")
        session_candidate = requests.Session()
        if load_session(session_candidate, cookies_path):
            profile = verify_session(session_candidate)
            if profile:
                session = session_candidate
                print_login_status("Session restored successfully", True)
            else:
                print_login_status("Session expired, will re-login", False)
        else:
            print_login_status("Failed to load session", False)

    if not session:
        print(f"{Colors.OKCYAN}[Step 2/3]{Colors.ENDC} Logging in with credentials...")
        time.sleep(2)
        session = xmulogin(type=3, username=USERNAME, password=PASSWORD)
        if session:
            save_session(session, cookies_path)
            print_login_status("Login successful", True)
        else:
            print_login_status("Login failed. Please check your credentials", False)
            time.sleep(5)
            sys.exit(1)

    print(f"{Colors.OKCYAN}[Step 3/3]{Colors.ENDC} Fetching user profile...")
    # profile = session.get(f"{base_url}/api/profile", headers=headers).json()
    # name = profile["name"]
    print_login_status(f"Welcome, {ACCOUNT_NAME}", True)

    print(f"\n{Colors.OKGREEN}{Colors.BOLD}Initialization complete{Colors.ENDC}")
    print(f"{Colors.GRAY}Monitor schedule: {schedule_description}{Colors.ENDC}")
    print(f"\n{Colors.GRAY}Starting monitor in 3 seconds...{Colors.ENDC}")
    time.sleep(3)

    # 主循环
    temp_data = {'rollcalls': []}
    query_count = 0
    start_time = time.time()
    rollcall_state = {
        "active_rollcall": "None",
        "sign_status": "Monitoring for new rollcalls",
        "status_color": Colors.GRAY,
    }
    monitor_state = {
        "status_text": "Active - Monitoring for new rollcalls...",
        "status_color": Colors.OKGREEN,
        "schedule_text": schedule_description,
    }
    next_relogin_allowed_at = 0.0
    relogin_alert_active = False
    initial_now_dt = datetime.now()
    initial_monitoring_allowed = is_in_schedule_window(monitor_schedule, initial_now_dt)

    if monitor_schedule.get("enabled"):
        if initial_monitoring_allowed:
            initial_window_end = get_current_window_end(monitor_schedule, initial_now_dt)
            initial_schedule_text = schedule_description
            if initial_window_end is not None:
                initial_schedule_text = (
                    f"{schedule_description} | Ends at "
                    f"{initial_window_end.strftime('%Y-%m-%d %H:%M')}"
                )
            monitor_state["status_text"] = "Active - Monitoring for new rollcalls..."
            monitor_state["status_color"] = Colors.OKGREEN
            monitor_state["schedule_text"] = initial_schedule_text
            rollcall_state["sign_status"] = "Monitoring for new rollcalls"
            rollcall_state["status_color"] = get_rollcall_status_color("pending")
        else:
            initial_next_start = get_next_schedule_start(monitor_schedule, initial_now_dt)
            initial_schedule_text = schedule_description
            if initial_next_start is not None:
                initial_schedule_text = (
                    f"{schedule_description} | Next start "
                    f"{initial_next_start.strftime('%Y-%m-%d %H:%M')}"
                )
            monitor_state["status_text"] = "Paused - Waiting for scheduled start"
            monitor_state["status_color"] = Colors.WARNING
            monitor_state["schedule_text"] = initial_schedule_text
            rollcall_state["sign_status"] = "Waiting for next monitor window"
            rollcall_state["status_color"] = get_rollcall_status_color("pending")
    else:
        initial_monitoring_allowed = True

    def update_rollcall_state(active_rollcall, sign_status, status_type="info"):
        if active_rollcall is None:
            rollcall_state["active_rollcall"] = "None"
        else:
            rollcall_state["active_rollcall"] = active_rollcall
        rollcall_state["sign_status"] = sign_status
        rollcall_state["status_color"] = get_rollcall_status_color(status_type)
        update_rollcall_status_lines(rollcall_state)

    def update_monitor_state(status_text, status_color, schedule_text):
        if (
            monitor_state.get("status_text") == status_text
            and monitor_state.get("status_color") == status_color
            and monitor_state.get("schedule_text") == schedule_text
        ):
            return
        monitor_state["status_text"] = status_text
        monitor_state["status_color"] = status_color
        monitor_state["schedule_text"] = schedule_text
        update_monitor_status_lines(monitor_state)

    def payload_requires_relogin(payload):
        if not isinstance(payload, dict):
            return False
        if "rollcalls" in payload:
            return False

        code_text = str(payload.get("code", "")).strip().lower()
        if code_text in {"401", "403", "unauthorized", "forbidden", "not_login"}:
            return True

        message_parts = [
            payload.get("message"),
            payload.get("msg"),
            payload.get("error"),
            payload.get("detail"),
            payload.get("description"),
        ]
        message_text = " ".join(str(part) for part in message_parts if part is not None).lower()
        keywords = ("login", "auth", "session", "expired", "未登录", "登录", "认证", "过期")
        return any(keyword in message_text for keyword in keywords)

    def response_looks_like_login_page(response):
        if response.status_code in (401, 403):
            return True

        content_type = response.headers.get("Content-Type", "").lower()
        if "application/json" in content_type:
            return False

        snippet = (response.text or "")[:600].lower()
        return any(
            token in snippet
            for token in (
                "authserver",
                "login",
                "/cas/",
                "统一身份认证",
                "sso",
            )
        )

    def relogin_session(reason):
        nonlocal session, next_relogin_allowed_at, relogin_alert_active

        now_ts = time.time()
        if now_ts < next_relogin_allowed_at:
            return False

        schedule_text = monitor_state.get("schedule_text", schedule_description)
        update_monitor_state("Re-authenticating session...", Colors.WARNING, schedule_text)
        update_rollcall_state(None, f"Session expired, re-login... ({reason})", "working")

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            new_session = xmulogin(type=3, username=USERNAME, password=PASSWORD)
            if new_session and verify_session(new_session):
                session = new_session
                save_session(session, cookies_path)
                next_relogin_allowed_at = 0.0
                relogin_alert_active = False
                update_rollcall_state(None, "Re-login successful, monitoring resumed", "success")
                update_monitor_state("Active - Monitoring for new rollcalls...", Colors.OKGREEN, schedule_text)
                return True
            if attempt < max_attempts:
                update_rollcall_state(
                    None,
                    f"Re-login attempt {attempt}/{max_attempts} failed, retrying...",
                    "working",
                )
                time.sleep(2)

        next_relogin_allowed_at = time.time() + 15
        update_rollcall_state(None, "Re-login failed, will retry later", "failure")
        update_monitor_state("Paused - Re-login failed", Colors.FAIL, schedule_text)
        if not relogin_alert_active:
            alert_title = "XMU Rollcall Bot 自动重登失败"
            alert_body = (
                f"账号: {ACCOUNT_NAME or USERNAME}\n"
                f"原因: {reason}\n"
                "监控已暂停，程序将继续自动重试重登。"
            )
            send_bark_message(alert_title, alert_body)
            relogin_alert_active = True
        return False

    def fetch_rollcalls_with_relogin():
        for _ in range(2):
            response = session.get(rollcalls_url, headers=headers, timeout=15)
            relogin_reason = None
            data = None

            if response_looks_like_login_page(response):
                relogin_reason = f"received status {response.status_code}"
            else:
                try:
                    data = response.json()
                except ValueError:
                    raise RuntimeError(
                        f"Unexpected non-JSON response from rollcalls API (status={response.status_code})"
                    )
                if payload_requires_relogin(data):
                    relogin_reason = "API reported unauthenticated session"
                elif not isinstance(data, dict) or "rollcalls" not in data:
                    raise RuntimeError("Unexpected rollcalls response format")

            if relogin_reason:
                if relogin_session(relogin_reason):
                    continue
                return None

            return data
        return None

    print_dashboard(
        ACCOUNT_NAME,
        start_time,
        query_count,
        0,
        show_banner=False,
        rollcall_state=rollcall_state,
        monitor_state=monitor_state,
    )

    footer_initialized = False
    last_displayed_elapsed = -1
    next_query_at = 0
    last_monitoring_allowed = initial_monitoring_allowed

    try:
        while True:
            try:
                time.sleep(0.1)
            except KeyboardInterrupt:
                raise

            try:
                current_time = time.time()
                now_dt = datetime.now()

                if not footer_initialized:
                    footer_initialized = True
                    update_footer_text()

                elapsed = int(current_time - start_time)
                if elapsed != last_displayed_elapsed:
                    last_displayed_elapsed = elapsed

                    local_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                    running_time = format_time(elapsed)

                    update_status_line(TIME_LINE, "Current Time:", local_time, Colors.OKCYAN)
                    update_status_line(RUNTIME_LINE, "Running Time:", running_time, Colors.OKGREEN)

                monitoring_allowed = is_in_schedule_window(monitor_schedule, now_dt)

                if monitor_schedule.get("enabled"):
                    if monitoring_allowed:
                        window_end = get_current_window_end(monitor_schedule, now_dt)
                        schedule_text = schedule_description
                        if window_end is not None:
                            schedule_text = (
                                f"{schedule_description} | Ends at "
                                f"{window_end.strftime('%Y-%m-%d %H:%M')}"
                            )
                        update_monitor_state(
                            "Active - Monitoring for new rollcalls...",
                            Colors.OKGREEN,
                            schedule_text,
                        )
                        if last_monitoring_allowed is not True:
                            update_rollcall_state(
                                None,
                                "Monitoring for new rollcalls",
                                "pending",
                            )
                            next_query_at = elapsed
                    else:
                        next_start = get_next_schedule_start(monitor_schedule, now_dt)
                        schedule_text = schedule_description
                        if next_start is not None:
                            schedule_text = (
                                f"{schedule_description} | Next start "
                                f"{next_start.strftime('%Y-%m-%d %H:%M')}"
                            )
                        update_monitor_state(
                            "Paused - Waiting for scheduled start",
                            Colors.WARNING,
                            schedule_text,
                        )
                        if last_monitoring_allowed is not False:
                            update_rollcall_state(
                                None,
                                "Waiting for next monitor window",
                                "pending",
                            )
                        last_monitoring_allowed = False
                        continue
                else:
                    update_monitor_state(
                        "Active - Monitoring for new rollcalls...",
                        Colors.OKGREEN,
                        schedule_description,
                    )

                last_monitoring_allowed = True

                if elapsed >= next_query_at:
                    next_query_at = elapsed + interval
                    data = fetch_rollcalls_with_relogin()
                    if data is None:
                        continue
                    query_count += 1

                    update_status_line(QUERY_LINE, "Query Count: ", str(query_count), Colors.WARNING)

                    if temp_data != data:
                        if len(data.get('rollcalls', [])) > 0:
                            if not verify_session(session):
                                if not relogin_session("session check failed before answering rollcall"):
                                    continue
                            print(f"\n{Colors.WARNING}{Colors.BOLD}New rollcall detected.{Colors.ENDC}")
                            temp_data = process_rollcalls(data, session, status_callback=update_rollcall_state)
                            update_rollcall_status_lines(rollcall_state)
                        else:
                            temp_data = data
            except KeyboardInterrupt:
                raise
            except Exception as e:
                clear_screen()
                print(f"\n{center_text(f'{Colors.FAIL}{Colors.BOLD}Error occurred:{Colors.ENDC} {str(e)}')}")
                print(f"{center_text(f'{Colors.GRAY}Exiting...{Colors.ENDC}')}\n")
                sys.exit(1)
    except KeyboardInterrupt:
        clear_screen()
        print(f"\n{center_text(f'{Colors.WARNING}Shutting down gracefully...{Colors.ENDC}')}")
        print(f"{center_text(f'{Colors.GRAY}Total queries performed: {query_count}{Colors.ENDC}')}")
        print(f"{center_text(f'{Colors.GRAY}Total running time: {format_time(int(time.time() - start_time))}{Colors.ENDC}')}")
        print(f"\n{center_text(f'{Colors.OKGREEN}Goodbye{Colors.ENDC}')}\n")
        sys.exit(0)
