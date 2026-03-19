import time

from .config import load_config
from .notification import send_bark_message
from .qr_handler import send_qr
from .verify import send_code, send_radar


def process_rollcalls(data, session, status_callback=None):
    data_empty = {"rollcalls": []}
    result = handle_rollcalls(data, session, status_callback=status_callback)
    if False in result:
        return data_empty
    return data


def extract_rollcalls(data):
    rollcalls = data["rollcalls"]
    result = []
    if rollcalls:
        rollcall_count = len(rollcalls)
        for rollcall in rollcalls:
            result.append(
                {
                    "course_title": rollcall["course_title"],
                    "created_by_name": rollcall["created_by_name"],
                    "department_name": rollcall["department_name"],
                    "is_expired": rollcall["is_expired"],
                    "is_number": rollcall["is_number"],
                    "is_radar": rollcall["is_radar"],
                    "rollcall_id": rollcall["rollcall_id"],
                    "rollcall_status": rollcall["rollcall_status"],
                    "scored": rollcall["scored"],
                    "status": rollcall["status"],
                }
            )
    else:
        rollcall_count = 0
    return rollcall_count, result


def get_rollcall_type(rollcall):
    if rollcall["is_radar"]:
        return "Radar rollcall"
    if rollcall["is_number"]:
        return "Number rollcall"
    return "QRcode rollcall"


def build_rollcall_message(rollcall, extra_message=""):
    parts = [
        f"Course: {rollcall['course_title']}",
        f"Teacher: {rollcall['department_name']} {rollcall['created_by_name']}",
        f"Type: {get_rollcall_type(rollcall)}",
        f"Status: {rollcall['status']}",
    ]
    if extra_message:
        parts.append(extra_message)
    return "\n".join(parts)


def notify_rollcall_event(rollcall, event_name, title, extra_message=""):
    send_bark_message(
        title,
        build_rollcall_message(rollcall, extra_message),
        dedupe_key=(rollcall["rollcall_id"], event_name),
    )


def _emit_status(status_callback, rollcall, status_text, status_type="info", index=None, total=None):
    if status_callback is None:
        return

    if rollcall is None:
        status_callback(None, status_text, status_type)
        return

    prefix = ""
    if index is not None and total is not None:
        prefix = f"[{index}/{total}] "

    active_rollcall = f"{prefix}{rollcall['course_title']} ({get_rollcall_type(rollcall)})"
    status_callback(active_rollcall, status_text, status_type)


def handle_rollcalls(data, session, status_callback=None):
    count, rollcalls = extract_rollcalls(data)
    answer_status = [False for _ in range(count)]

    if count:
        print(time.strftime("%H:%M:%S", time.localtime()), "New rollcall(s) found!\n")
        config_data = load_config()
        ngrok_token = config_data.get("ngrok_token", "")

        for i in range(count):
            rollcall = rollcalls[i]

            print(f"{i + 1} of {count}:")
            print(
                f"Course name: {rollcall['course_title']}, "
                f"rollcall created by {rollcall['department_name']} {rollcall['created_by_name']}."
            )

            temp_str = get_rollcall_type(rollcall)
            print(f"Rollcall type: {temp_str}\n")
            notify_rollcall_event(rollcall, "detected", "Detected new rollcall")
            _emit_status(status_callback, rollcall, "Detected, preparing to handle", "pending", i + 1, count)

            if (rollcall["status"] == "absent") & (rollcall["is_number"]) & (not rollcall["is_radar"]):
                _emit_status(status_callback, rollcall, "Trying number rollcall", "working", i + 1, count)
                if send_code(session, rollcall["rollcall_id"]):
                    answer_status[i] = True
                    notify_rollcall_event(rollcall, "answered_success", "Auto rollcall succeeded")
                    _emit_status(
                        status_callback,
                        rollcall,
                        "Number rollcall answered successfully",
                        "success",
                        i + 1,
                        count,
                    )
                else:
                    print("Answering failed.")
                    notify_rollcall_event(rollcall, "answered_failed", "Auto rollcall failed")
                    _emit_status(status_callback, rollcall, "Number rollcall failed", "failure", i + 1, count)
            elif rollcall["status"] == "on_call_fine":
                print("Already answered.")
                answer_status[i] = True
                notify_rollcall_event(rollcall, "already_answered", "Rollcall already answered")
                _emit_status(status_callback, rollcall, "Already answered", "success", i + 1, count)
            elif rollcall["is_radar"]:
                _emit_status(status_callback, rollcall, "Trying radar rollcall", "working", i + 1, count)
                if send_radar(session, rollcall["rollcall_id"]):
                    answer_status[i] = True
                    notify_rollcall_event(rollcall, "answered_success", "Auto rollcall succeeded")
                    _emit_status(
                        status_callback,
                        rollcall,
                        "Radar rollcall answered successfully",
                        "success",
                        i + 1,
                        count,
                    )
                else:
                    print("Answering failed.")
                    notify_rollcall_event(rollcall, "answered_failed", "Auto rollcall failed")
                    _emit_status(status_callback, rollcall, "Radar rollcall failed", "failure", i + 1, count)
            else:
                notify_rollcall_event(rollcall, "qr_waiting", "QR rollcall detected", "Waiting for QR scan.")
                _emit_status(status_callback, rollcall, "Waiting for QR scan", "pending", i + 1, count)
                if send_qr(session, rollcall["rollcall_id"], ngrok_token):
                    answer_status[i] = True
                    notify_rollcall_event(rollcall, "answered_success", "QR rollcall succeeded")
                    _emit_status(
                        status_callback,
                        rollcall,
                        "QR rollcall answered successfully",
                        "success",
                        i + 1,
                        count,
                    )
                else:
                    print("Answering failed.")
                    notify_rollcall_event(rollcall, "answered_failed", "QR rollcall failed")
                    _emit_status(status_callback, rollcall, "QR rollcall failed", "failure", i + 1, count)

        _emit_status(status_callback, None, "Monitoring for new rollcalls", "idle")

    return answer_status
