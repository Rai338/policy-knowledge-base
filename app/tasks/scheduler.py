"""采集调度（CRAWL-002 分级轮询）：核心源 5 分钟、一般源 30 分钟、长尾源每日。

使用 APScheduler 后台调度；信源新增/修改后调用 sync() 重新装载任务。
"""
from __future__ import annotations

from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import CRAWL_ENABLED
from app.core.constants import CRAWL_FREQ
from app.core.logging import logger
from app.db.database import SessionLocal
from app.db.models import CrawlSource
from app.services import crawl_service


class CrawlScheduler:
    def __init__(self):
        self.scheduler: Optional[BackgroundScheduler] = None

    def start(self) -> None:
        if not CRAWL_ENABLED:
            logger.info("采集调度已关闭（PKB_CRAWL_ENABLED=false）")
            return
        if self.scheduler and self.scheduler.running:
            return
        self.scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        self.scheduler.start()
        self.sync()
        logger.info("采集调度已启动")

    def sync(self) -> int:
        """按当前信源配置装载/刷新定时任务。"""
        if not self.scheduler:
            return 0
        db = SessionLocal()
        try:
            sources = db.query(CrawlSource).filter(CrawlSource.enabled.is_(True)).all()
            wanted = {}
            for source in sources:
                minutes = CRAWL_FREQ.get(source.frequency, CRAWL_FREQ["NORMAL"])["minutes"]
                wanted[source.id] = minutes
            for job in list(self.scheduler.get_jobs()):
                if job.id not in wanted:
                    job.remove()
            for source_id, minutes in wanted.items():
                self.scheduler.add_job(
                    self._run,
                    trigger=IntervalTrigger(minutes=minutes),
                    id=source_id,
                    name=f"crawl:{source_id}",
                    args=[source_id],
                    replace_existing=True,
                    max_instances=1,
                    misfire_grace_time=300,
                )
            logger.info("采集任务装载完成：%s 个信源", len(wanted))
            return len(wanted)
        finally:
            db.close()

    @staticmethod
    def _run(source_id: str) -> None:
        db = SessionLocal()
        try:
            crawl_service.run_source(db, source_id, operator="scheduler")
        except Exception as exc:  # pragma: no cover
            logger.exception("定时采集异常（%s）：%s", source_id, exc)
        finally:
            db.close()

    def stop(self) -> None:
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("采集调度已停止")

    def jobs(self) -> list:
        if not self.scheduler:
            return []
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.next_run_time else "",
            }
            for job in self.scheduler.get_jobs()
        ]


scheduler = CrawlScheduler()
