"""
CronScheduler — Schedule and execute companion skill tasks.

Uses APScheduler to run cron-triggered skills at their defined schedules.
Each cron task creates a temporary ChatAgent, generates a message,
and pushes it to connected clients.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Optional, Callable, Awaitable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from agent.skills.skill_engine import Skill


# Type alias for the callback that delivers cron messages
CronMessageCallback = Callable[[str, str, str], Awaitable[None]]
# callback(persona_id, skill_id, generated_message)


class CronScheduler:
    """
    Schedule cron-triggered skills and deliver generated messages.

    Usage:
        scheduler = CronScheduler()
        scheduler.set_message_generator(my_generator_func)
        scheduler.set_message_callback(my_delivery_func)
        scheduler.register_skills(skill_engine.get_cron_skills())
        scheduler.start()
    """

    def __init__(self):
        self._scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
        self._generate_fn: Optional[Callable] = None
        self._callback_fn: Optional[CronMessageCallback] = None
        self._registered: list[str] = []

    def set_message_generator(
        self,
        fn: Callable[[str, str], Awaitable[str]],
    ) -> None:
        """
        Set the function that generates cron messages.

        fn(skill_prompt, persona_id) -> generated_message
        """
        self._generate_fn = fn

    def set_message_callback(self, fn: CronMessageCallback) -> None:
        """
        Set the callback that delivers generated cron messages.

        fn(persona_id, skill_id, message) -> None
        """
        self._callback_fn = fn

    def register_skills(
        self,
        skills: list[Skill],
        persona_ids: Optional[list[str]] = None,
    ) -> None:
        """
        Register cron skills with the scheduler.

        For each skill × persona combination, a job is created.
        """
        if not persona_ids:
            print("[cron] ⚠️ No persona_ids provided, skipping registration")
            return

        for skill in skills:
            if not skill.cron_schedule:
                continue

            try:
                trigger = CronTrigger.from_crontab(
                    skill.cron_schedule,
                    timezone="Asia/Shanghai",
                )
            except ValueError as e:
                print(f"[cron] 无效的 cron 表达式 '{skill.cron_schedule}' ({skill.name}): {e}")
                continue

            for persona_id in persona_ids:
                job_id = f"{skill.skill_id}_{persona_id}"
                self._scheduler.add_job(
                    self._execute_skill,
                    trigger=trigger,
                    id=job_id,
                    name=f"{skill.name} ({persona_id})",
                    kwargs={
                        "skill": skill,
                        "persona_id": persona_id,
                    },
                    replace_existing=True,
                )
                self._registered.append(job_id)

        print(f"✓ Cron 调度器: 注册了 {len(self._registered)} 个定时任务")

    async def _execute_skill(self, skill: Skill, persona_id: str) -> None:
        """Execute a single cron skill trigger."""
        if not self._generate_fn or not self._callback_fn:
            print(f"[cron] 跳过 {skill.name}: 生成器或回调未设置")
            return

        try:
            print(f"[cron] 触发: {skill.name} → {persona_id}")

            # Build the skill's prompt for generation
            prompt = skill.prompt_injection or skill.description
            message = await self._generate_fn(prompt, persona_id)

            if message:
                await self._callback_fn(persona_id, skill.skill_id, message)
                print(f"[cron] ✓ {skill.name}: {message[:50]}...")
            else:
                print(f"[cron] ✗ {skill.name}: 生成为空")

        except Exception as e:
            print(f"[cron] ✗ {skill.name} 执行错误: {e}")

    def start(self) -> None:
        """Start the scheduler."""
        if not self._scheduler.running:
            self._scheduler.start()
            # Print next fire times
            jobs = self._scheduler.get_jobs()
            for job in jobs:
                next_run = job.next_run_time
                if next_run:
                    print(f"  → {job.name}: 下次 {next_run.strftime('%H:%M')}")

    def stop(self) -> None:
        """Stop the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def get_jobs_info(self) -> list[dict]:
        """Get info about all scheduled jobs."""
        jobs = self._scheduler.get_jobs()
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
            }
            for job in jobs
        ]
