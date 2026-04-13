import click
import sys
import requests
from xmulogin import xmulogin
from .config import (
    load_config, save_config, is_config_complete, get_cookies_path,
    add_account, get_all_accounts, get_current_account, set_current_account,
    get_account_by_id, CONFIG_FILE, delete_account, perform_account_deletion,
    normalize_monitor_schedule
)
from .monitor import start_monitor, base_url, headers
from .notification import send_bark_message
from . import __version__

# ANSI Color codes
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    GRAY = '\033[90m'


WEEKDAY_LABELS = {
    1: "Mon",
    2: "Tue",
    3: "Wed",
    4: "Thu",
    5: "Fri",
    6: "Sat",
    7: "Sun",
}


def check_pypi_version():
    """Check if the current version is the latest on PyPI."""
    try:
        resp = requests.get(
            "https://pypi.org/pypi/xmu-rollcall-cli/json", timeout=5
        )
        if resp.status_code == 200:
            latest = resp.json()["info"]["version"]
            if _parse_version(latest) > _parse_version(__version__):
                click.echo(
                    f"{Colors.WARNING}新版本可用: v{latest}（当前: v{__version__}），"
                    f"请运行 pip install -U xmu-rollcall-cli 进行更新{Colors.ENDC}"
                )
    except Exception:
        pass


def _parse_version(v):
    """Parse a version string into a comparable tuple of ints."""
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0,)


def save_bark_url_and_send_test(config, bark_url):
    bark_url = bark_url.strip()
    config["bark_url"] = bark_url
    save_config(config)
    if not bark_url:
        return None
    return send_bark_message(
        "XMU Rollcall Bot Test",
        "If you received this message, Bark notifications are working.",
        bark_url=bark_url,
    )


def format_monitor_schedule(schedule):
    """格式化监控时段配置用于显示。"""
    schedule = normalize_monitor_schedule(schedule)
    if not schedule.get("enabled"):
        return "Disabled (always on)"

    days = schedule.get("days", [])
    if days == [1, 2, 3, 4, 5, 6, 7]:
        days_text = "Every day"
    else:
        days_text = ", ".join(WEEKDAY_LABELS.get(day, str(day)) for day in days)
    return f"{days_text} {schedule.get('start_time')} - {schedule.get('end_time')}"


def format_days_for_prompt(days):
    """将星期列表格式化为配置输入默认值。"""
    normalized = normalize_monitor_schedule({"days": days})
    if normalized.get("days") == [1, 2, 3, 4, 5, 6, 7]:
        return "all"
    return ",".join(str(day) for day in normalized.get("days", []))


def parse_schedule_days(days_text):
    """解析星期输入，支持 all 或 1,2,3 形式。"""
    text = days_text.strip().lower()
    if text in {"all", "everyday", "daily"}:
        return [1, 2, 3, 4, 5, 6, 7]

    raw_parts = [part.strip() for part in text.split(",")]
    days = []
    for part in raw_parts:
        if not part:
            continue
        if not part.isdigit():
            raise ValueError("Days must be numbers from 1 to 7, separated by commas.")
        day = int(part)
        if day < 1 or day > 7:
            raise ValueError("Days must be in the range 1 to 7.")
        if day not in days:
            days.append(day)

    if not days:
        raise ValueError("Please provide at least one weekday.")
    return sorted(days)


def is_valid_time_text(value):
    """校验时间格式是否为 HH:MM。"""
    if len(value) != 5 or value[2] != ":":
        return False
    hour_text, minute_text = value.split(":")
    if not (hour_text.isdigit() and minute_text.isdigit()):
        return False
    hour = int(hour_text)
    minute = int(minute_text)
    return 0 <= hour <= 23 and 0 <= minute <= 59


def prompt_time_value(label, default):
    """循环提示直到输入合法的 HH:MM 时间。"""
    while True:
        value = click.prompt(label, default=default).strip()
        if is_valid_time_text(value):
            return value
        click.echo(f"{Colors.FAIL}✗ Invalid time format. Please use HH:MM, e.g. 08:00 or 22:00.{Colors.ENDC}")

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    if ctx.invoked_subcommand is None:
        click.echo(f"{Colors.OKCYAN}{Colors.BOLD}XMU Rollcall Bot CLI v3.3.1{Colors.ENDC}")
        click.echo(f"\nUsage:")
        click.echo(f"  xmu config    Configure credentials and add accounts")
        click.echo(f"  xmu switch    Switch between accounts")
        click.echo(f"  xmu start     Start monitoring rollcalls")
        click.echo(f"  xmu refresh   Refresh the login status")
        click.echo(f"  xmu --help    Show this message")

@cli.command()
def config():
    """配置账号：添加、删除账号"""
    click.echo(f"\n{Colors.BOLD}{Colors.OKCYAN}=== XMU Rollcall Configuration ==={Colors.ENDC}\n")

    current_config = load_config()

    def show_accounts():
        """显示账号列表"""
        accounts = get_all_accounts(current_config)
        if accounts:
            click.echo(f"{Colors.BOLD}Existing accounts:{Colors.ENDC}")
            current_account = get_current_account(current_config)
            for acc in accounts:
                current_marker = f" {Colors.OKGREEN}(current){Colors.ENDC}" if current_account and acc.get("id") == current_account.get("id") else ""
                click.echo(f"  {acc.get('id')}: {acc.get('name') or acc.get('username')}{current_marker}")
            click.echo()
        else:
            click.echo(f"{Colors.GRAY}No accounts configured.{Colors.ENDC}\n")

    def add_new_account():
        """添加新账号"""
        click.echo(f"{Colors.BOLD}Adding a new account...{Colors.ENDC}\n")

        # 输入新账号信息
        username = click.prompt(f"{Colors.BOLD}Username{Colors.ENDC}")
        password = click.prompt(f"{Colors.BOLD}Password{Colors.ENDC}", hide_input=False)

        # 验证登录
        click.echo(f"\n{Colors.OKCYAN}Validating credentials...{Colors.ENDC}")
        try:
            session = xmulogin(type=3, username=username, password=password)
            if session:
                click.echo(f"{Colors.OKGREEN}✓ Login successful!{Colors.ENDC}")

                # 获取用户姓名
                click.echo(f"{Colors.OKCYAN}Fetching user profile...{Colors.ENDC}")
                try:
                    profile = session.get(f"{base_url}/api/profile", headers=headers).json()
                    name = profile.get("name", "")
                    click.echo(f"{Colors.OKGREEN}✓ Welcome, {name}!{Colors.ENDC}")
                except Exception:
                    click.echo(f"{Colors.WARNING}⚠ Could not fetch profile, using username as name{Colors.ENDC}")
                    name = username

                # 添加账号
                try:
                    account_id = add_account(current_config, username, password, name)
                    save_config(current_config)

                    click.echo(f"{Colors.OKGREEN}✓ Account added successfully! (ID: {account_id}){Colors.ENDC}")
                    click.echo(f"{Colors.GRAY}Configuration file: {CONFIG_FILE}{Colors.ENDC}\n")
                except RuntimeError as e:
                    click.echo(f"{Colors.FAIL}✗ Failed to save configuration: {str(e)}{Colors.ENDC}")
                    click.echo(f"{Colors.WARNING}Tip: In sandboxed environments (like a-Shell), set environment variable:{Colors.ENDC}")
                    click.echo(f"  export XMU_ROLLCALL_CONFIG_DIR=~/Documents/.xmu_rollcall")
            else:
                click.echo(f"{Colors.FAIL}✗ Login failed. Please check your credentials.{Colors.ENDC}")
        except Exception as e:
            click.echo(f"{Colors.FAIL}✗ Error during login validation: {str(e)}{Colors.ENDC}")

    def delete_existing_account():
        """删除账号"""
        accounts = get_all_accounts(current_config)
        if not accounts:
            click.echo(f"{Colors.WARNING}No accounts to delete.{Colors.ENDC}\n")
            return

        show_accounts()

        # 让用户选择要删除的账号
        valid_ids = [str(acc.get("id")) for acc in accounts]
        selected_id = click.prompt(
            f"{Colors.BOLD}Enter account ID to delete{Colors.ENDC}",
            type=click.Choice(valid_ids, case_sensitive=False)
        )

        selected_id = int(selected_id)
        selected_account = get_account_by_id(current_config, selected_id)

        if selected_account:
            # 确认删除
            confirm = click.prompt(
                f"{Colors.WARNING}Are you sure you want to delete account '{selected_account.get('name') or selected_account.get('username')}' (ID: {selected_id})?{Colors.ENDC}",
                type=click.Choice(['y', 'n'], case_sensitive=False),
                default='n'
            )

            if confirm.lower() == 'y':
                # 执行删除
                success, cookies_to_delete, cookies_to_rename = delete_account(current_config, selected_id)

                if success:
                    # 保存配置
                    save_config(current_config)

                    # 处理cookies文件
                    perform_account_deletion(cookies_to_delete, cookies_to_rename)

                    click.echo(f"{Colors.OKGREEN}✓ Account deleted successfully!{Colors.ENDC}")

                    # 显示ID变更提示
                    if cookies_to_rename:
                        click.echo(f"{Colors.GRAY}Note: Account IDs have been re-assigned.{Colors.ENDC}")
                    click.echo()
                else:
                    click.echo(f"{Colors.FAIL}✗ Failed to delete account.{Colors.ENDC}\n")
            else:
                click.echo(f"{Colors.GRAY}Deletion cancelled.{Colors.ENDC}\n")
        else:
            click.echo(f"{Colors.FAIL}✗ Account not found.{Colors.ENDC}\n")

    def configure_monitor_schedule():
        """配置监控时段"""
        current_schedule = normalize_monitor_schedule(
            current_config.get("monitor_schedule")
        )

        click.echo(f"{Colors.BOLD}Configure monitor schedule{Colors.ENDC}")
        click.echo(
            f"{Colors.GRAY}Current schedule: {format_monitor_schedule(current_schedule)}{Colors.ENDC}"
        )
        click.echo(
            f"{Colors.GRAY}Weekdays: 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat, 7=Sun{Colors.ENDC}\n"
        )

        enabled = click.prompt(
            f"{Colors.BOLD}Enable monitor schedule? (y/n){Colors.ENDC}",
            type=click.Choice(["y", "n"], case_sensitive=False),
            default="y" if current_schedule.get("enabled") else "n",
        )

        if enabled.lower() == "n":
            current_schedule["enabled"] = False
            current_config["monitor_schedule"] = current_schedule
            save_config(current_config)
            click.echo(f"{Colors.OKGREEN}✓ Monitor schedule disabled. Monitoring will stay on all day.{Colors.ENDC}\n")
            return

        while True:
            days_input = click.prompt(
                f"{Colors.BOLD}Days{Colors.ENDC}",
                default=format_days_for_prompt(current_schedule.get("days", [])),
            )
            try:
                selected_days = parse_schedule_days(days_input)
                break
            except ValueError as e:
                click.echo(f"{Colors.FAIL}✗ {str(e)}{Colors.ENDC}")

        start_time = prompt_time_value(
            f"{Colors.BOLD}Start Time{Colors.ENDC}",
            current_schedule.get("start_time", "08:00"),
        )
        end_time = prompt_time_value(
            f"{Colors.BOLD}End Time{Colors.ENDC}",
            current_schedule.get("end_time", "22:00"),
        )

        current_config["monitor_schedule"] = normalize_monitor_schedule({
            "enabled": True,
            "days": selected_days,
            "start_time": start_time,
            "end_time": end_time,
        })
        save_config(current_config)
        click.echo(
            f"{Colors.OKGREEN}✓ Monitor schedule saved: "
            f"{format_monitor_schedule(current_config['monitor_schedule'])}.{Colors.ENDC}\n"
        )

    # 主循环
    while True:
        show_accounts()

        # 显示 ngrok token 配置状态
        ngrok_token = current_config.get("ngrok_token", "")
        if ngrok_token:
            click.echo(f"{Colors.BOLD}Ngrok Token:{Colors.ENDC} {Colors.OKGREEN}Configured{Colors.ENDC}")
        else:
            click.echo(f"{Colors.BOLD}Ngrok Token:{Colors.ENDC} {Colors.GRAY}Not configured (required for QR code rollcall){Colors.ENDC}")

        bark_url = current_config.get("bark_url", "")
        if bark_url:
            click.echo(f"{Colors.BOLD}Bark URL:{Colors.ENDC} {Colors.OKGREEN}Configured{Colors.ENDC}")
        else:
            click.echo(f"{Colors.BOLD}Bark URL:{Colors.ENDC} {Colors.GRAY}Not configured (optional push notifications){Colors.ENDC}")

        # 显示轮询间隔配置
        monitor_interval = current_config.get("monitor_interval", 1)
        click.echo(f"{Colors.BOLD}Monitor Interval:{Colors.ENDC} {Colors.OKCYAN}{monitor_interval} second(s){Colors.ENDC}")
        rollcall_sign_delay = current_config.get("rollcall_sign_delay", 30)
        click.echo(f"{Colors.BOLD}Sign Delay:{Colors.ENDC}      {Colors.OKCYAN}{rollcall_sign_delay} second(s){Colors.ENDC}")
        monitor_schedule = normalize_monitor_schedule(current_config.get("monitor_schedule"))
        schedule_color = Colors.OKCYAN if monitor_schedule.get("enabled") else Colors.GRAY
        click.echo(
            f"{Colors.BOLD}Monitor Schedule:{Colors.ENDC} "
            f"{schedule_color}{format_monitor_schedule(monitor_schedule)}{Colors.ENDC}"
        )
        click.echo()

        click.echo(f"{Colors.BOLD}Choose an action:{Colors.ENDC}")
        click.echo(f"  {Colors.OKCYAN}n{Colors.ENDC} - Add new account")
        click.echo(f"  {Colors.OKCYAN}d{Colors.ENDC} - Delete account")
        click.echo(f"  {Colors.OKCYAN}t{Colors.ENDC} - Configure ngrok token (for QR code rollcall)")
        click.echo(f"  {Colors.OKCYAN}b{Colors.ENDC} - Configure Bark URL (for push notifications)")
        click.echo(f"  {Colors.OKCYAN}i{Colors.ENDC} - Set monitor interval")
        click.echo(f"  {Colors.OKCYAN}r{Colors.ENDC} - Set sign delay after rollcall detection")
        click.echo(f"  {Colors.OKCYAN}s{Colors.ENDC} - Configure monitor schedule")
        click.echo(f"  {Colors.OKCYAN}q{Colors.ENDC} - Quit")

        action = click.prompt(
            f"\n{Colors.BOLD}Action{Colors.ENDC}",
            type=click.Choice(['n', 'd', 't', 'b', 'i', 'r', 's', 'q'], case_sensitive=False),
            default='q'
        )

        click.echo()

        if action.lower() == 'n':
            add_new_account()
        elif action.lower() == 'd':
            delete_existing_account()
        elif action.lower() == 't':
            # Configure ngrok token
            click.echo(f"{Colors.BOLD}Configure ngrok token for QR code rollcall{Colors.ENDC}")
            click.echo(f"{Colors.GRAY}Get your token at: https://ngrok.com/ -> Your Authtoken{Colors.ENDC}\n")
            token = click.prompt(f"{Colors.BOLD}Ngrok Token{Colors.ENDC}", default=current_config.get("ngrok_token", ""))
            current_config["ngrok_token"] = token
            save_config(current_config)
            click.echo(f"{Colors.OKGREEN}✓ Ngrok token saved.{Colors.ENDC}\n")
        elif action.lower() == 'b':
            click.echo(f"{Colors.BOLD}Configure Bark URL for push notifications{Colors.ENDC}")
            click.echo(f"{Colors.GRAY}Example: https://api.day.app/your_device_key{Colors.ENDC}")
            click.echo(f"{Colors.GRAY}Leave empty to disable Bark notifications.{Colors.ENDC}\n")
            bark_url = click.prompt(
                f"{Colors.BOLD}Bark URL{Colors.ENDC}",
                default=current_config.get("bark_url", ""),
                show_default=False
            ).strip()
            test_result = save_bark_url_and_send_test(current_config, bark_url)
            if bark_url:
                click.echo(f"{Colors.OKGREEN}Bark URL saved.{Colors.ENDC}")
                click.echo(f"{Colors.OKCYAN}Sending test notification...{Colors.ENDC}")
                if test_result:
                    click.echo(f"{Colors.OKGREEN}✓ Test notification sent. Check your Bark device.{Colors.ENDC}\n")
                else:
                    click.echo(
                        f"{Colors.WARNING}⚠ Test notification failed. "
                        f"Please check the Bark URL and device status.{Colors.ENDC}\n"
                    )
            else:
                click.echo(f"{Colors.OKGREEN}Bark notifications disabled.{Colors.ENDC}\n")
        elif action.lower() == 'i':
            # Configure monitor interval
            click.echo(f"{Colors.BOLD}Set monitor polling interval{Colors.ENDC}")
            click.echo(f"{Colors.GRAY}Interval in seconds between each rollcall check (minimum: 1){Colors.ENDC}\n")
            current_interval = current_config.get("monitor_interval", 1)
            new_interval = click.prompt(
                f"{Colors.BOLD}Interval (seconds){Colors.ENDC}",
                type=int,
                default=current_interval
            )
            if new_interval < 1:
                click.echo(f"{Colors.WARNING}⚠ Interval must be at least 1 second, setting to 1.{Colors.ENDC}")
                new_interval = 1
            current_config["monitor_interval"] = new_interval
            save_config(current_config)
            click.echo(f"{Colors.OKGREEN}✓ Monitor interval set to {new_interval} second(s).{Colors.ENDC}\n")
        elif action.lower() == 'r':
            click.echo(f"{Colors.BOLD}Set sign delay after rollcall detection{Colors.ENDC}")
            click.echo(f"{Colors.GRAY}Delay before attempting sign-in when a new rollcall is detected (minimum: 0){Colors.ENDC}\n")
            current_delay = current_config.get("rollcall_sign_delay", 30)
            new_delay = click.prompt(
                f"{Colors.BOLD}Delay (seconds){Colors.ENDC}",
                type=int,
                default=current_delay
            )
            if new_delay < 0:
                click.echo(f"{Colors.WARNING}⚠ Delay cannot be negative, setting to 0.{Colors.ENDC}")
                new_delay = 0
            current_config["rollcall_sign_delay"] = new_delay
            save_config(current_config)
            click.echo(f"{Colors.OKGREEN}✓ Sign delay set to {new_delay} second(s).{Colors.ENDC}\n")
        elif action.lower() == 's':
            configure_monitor_schedule()
        elif action.lower() == 'q':
            # 退出前显示最终账号列表
            accounts = get_all_accounts(current_config)
            if accounts:
                click.echo(f"{Colors.BOLD}Final account list:{Colors.ENDC}")
                current_account = get_current_account(current_config)
                for acc in accounts:
                    current_marker = f" {Colors.OKGREEN}(current){Colors.ENDC}" if current_account and acc.get("id") == current_account.get("id") else ""
                    click.echo(f"  {acc.get('id')}: {acc.get('name') or acc.get('username')}{current_marker}")
                click.echo(f"\n{Colors.GRAY}You can run: {Colors.BOLD}xmu switch{Colors.ENDC} to switch between accounts")
                click.echo(f"{Colors.GRAY}You can run: {Colors.BOLD}xmu start{Colors.ENDC} to start monitoring")
            break

@cli.command()
def start():
    """启动签到监控"""
    # 加载配置
    config_data = load_config()

    # 检查配置是否完整
    if not is_config_complete(config_data):
        click.echo(f"{Colors.FAIL}✗ Configuration incomplete!{Colors.ENDC}")
        click.echo(f"Please run: {Colors.BOLD}xmu config{Colors.ENDC}")
        sys.exit(1)

    # 获取当前账号
    current_account = get_current_account(config_data)
    click.echo(f"{Colors.OKCYAN}Using account: {current_account.get('name') or current_account.get('username')} (ID: {current_account.get('id')}){Colors.ENDC}")
    click.echo(
        f"{Colors.OKCYAN}Monitor schedule: "
        f"{format_monitor_schedule(config_data.get('monitor_schedule'))}{Colors.ENDC}"
    )
    click.echo(
        f"{Colors.OKCYAN}Sign delay after detection: "
        f"{config_data.get('rollcall_sign_delay', 30)} second(s){Colors.ENDC}"
    )

    # 检查 PyPI 上是否有新版本
    check_pypi_version()

    # 启动监控
    try:
        start_monitor(current_account)
    except KeyboardInterrupt:
        click.echo(f"\n{Colors.WARNING}Shutting down...{Colors.ENDC}")
        sys.exit(0)
    except Exception as e:
        click.echo(f"\n{Colors.FAIL}Error: {str(e)}{Colors.ENDC}")
        sys.exit(1)

@cli.command()
def refresh():
    """清除当前账号的登录缓存"""
    config_data = load_config()
    current_account = get_current_account(config_data)

    if not current_account:
        click.echo(f"{Colors.FAIL}✗ No account configured!{Colors.ENDC}")
        click.echo(f"Please run: {Colors.BOLD}xmu config{Colors.ENDC}")
        sys.exit(1)

    account_id = current_account.get("id")
    cookies_path = get_cookies_path(account_id)
    try:
        click.echo(f"\n{Colors.WARNING}Deleting cookies for account {account_id} ({current_account.get('name')})...{Colors.ENDC}")
        # delete cookies file
        import os
        if os.path.exists(cookies_path):
            os.remove(cookies_path)
            click.echo(f"{Colors.OKGREEN}✓ Cookies deleted successfully.{Colors.ENDC}")
        else:
            click.echo(f"{Colors.GRAY}No cookies file found to delete.{Colors.ENDC}")
        sys.exit(0)
    except Exception as e:
        click.echo(f"{Colors.FAIL}✗ Failed to delete cookies: {str(e)}{Colors.ENDC}")
        sys.exit(1)


@cli.command()
def switch():
    """切换当前使用的账号"""
    click.echo(f"\n{Colors.BOLD}{Colors.OKCYAN}=== Switch Account ==={Colors.ENDC}\n")

    config_data = load_config()
    accounts = get_all_accounts(config_data)

    if not accounts:
        click.echo(f"{Colors.FAIL}✗ No accounts configured!{Colors.ENDC}")
        click.echo(f"Please run: {Colors.BOLD}xmu config{Colors.ENDC}")
        sys.exit(1)

    current_account = get_current_account(config_data)
    current_id = current_account.get("id") if current_account else None

    # 显示账号列表
    click.echo(f"{Colors.BOLD}Available accounts:{Colors.ENDC}")
    for acc in accounts:
        current_marker = f" {Colors.OKGREEN}(current){Colors.ENDC}" if acc.get("id") == current_id else ""
        click.echo(f"  {acc.get('id')}: {acc.get('name') or acc.get('username')}{current_marker}")

    click.echo()

    # 让用户选择账号
    valid_ids = [str(acc.get("id")) for acc in accounts]
    selected_id = click.prompt(
        f"{Colors.BOLD}Enter account ID to switch to{Colors.ENDC}",
        type=click.Choice(valid_ids, case_sensitive=False)
    )

    selected_id = int(selected_id)
    selected_account = get_account_by_id(config_data, selected_id)

    if selected_account:
        set_current_account(config_data, selected_id)
        save_config(config_data)
        click.echo(f"\n{Colors.OKGREEN}✓ Switched to account: {selected_account.get('name') or selected_account.get('username')} (ID: {selected_id}){Colors.ENDC}")
        click.echo(f"{Colors.GRAY}You can now run: {Colors.BOLD}xmu start{Colors.ENDC}")
    else:
        click.echo(f"{Colors.FAIL}✗ Account not found!{Colors.ENDC}")
        sys.exit(1)


if __name__ == '__main__':
    cli()
