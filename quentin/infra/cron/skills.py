from __future__ import annotations

from .manager import cron_engine

class CronSkills:
    """
    Brain skills to manage recurring schedules.
    """
    @staticmethod
    async def schedule_recurring(name: str, interval_minutes: int, command: str) -> str:
        """Schedules a task to run every X minutes."""
        cron_engine.schedule_task(name, interval_minutes * 60, command)
        return f"Task '{name}' scheduled every {interval_minutes} minutes."

    @staticmethod
    async def list_tasks() -> str:
        """Lists all active cron tasks."""
        if not cron_engine._tasks:
            return "No scheduled tasks."
        
        lines = ["Active Scheduled Tasks:"]
        for name, task in cron_engine._tasks.items():
            lines.append(f"- {name}: '{task['input']}' (every {task['interval']//60}m)")
        return "\n".join(lines)
