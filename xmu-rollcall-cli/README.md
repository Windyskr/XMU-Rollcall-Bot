# XMU Rollcall CLI

CLI tool for monitoring and handling rollcalls on Xiamen University Tronclass.

## Quick Notes

- Run `xmu config` to configure accounts, polling interval, and monitor schedule.
- Monitor schedule supports weekly recurring windows such as `08:00` to `22:00`.
- Days use `1-7` for `Mon-Sun`, and `all` means every day.
- Run `xmu start` to begin monitoring; when schedule is enabled it will wait outside the configured window and resume automatically at the next start time.
