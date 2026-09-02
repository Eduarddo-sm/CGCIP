from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from database.repository import Repository
from monitoring.file_monitor import FileMonitor
from services.attachment_storage import AttachmentStorageService
from services.background_optimizer import BackgroundOptimizer
from services.backup_retention import BackupRetentionService
from services.colchao_service import ColchaoService
from services.database_backup import DatabaseBackupService
from services.database_maintenance import DatabaseMaintenanceService
from services.database_monitoring import DatabaseMonitoringService
from services.defasagem_service import DefasagemService
from services.excel_reader import ExcelReader
from services.alpha_ho_service import AlphaHonorariosService
from services.main_hub_service import MainHubService
from services.maintenance_scheduler import MaintenanceScheduler, ScheduledJob
from services.negociador_service import NegotiadorService
from services.negocial_service import NegocialService
from services.negocial_tool_builder_service import NegocialToolBuilderService
from services.notification_service import NotificationService
from services.overview_service import OverviewService
from services.parecer_service import ParecerService
from services.production_analytics_service import ProductionAnalyticsService
from services.protocolo_service import ProtocoloService


logger = logging.getLogger("gerencial.app_state")


class AppState:
    """Application composition root and background-job lifecycle."""

    def __init__(self, root: Path, data_dir: Path, database_url: str) -> None:
        data_dir.mkdir(exist_ok=True)
        self.repo = Repository(database_url)
        self.reader = ExcelReader()
        self.negocial = NegocialService(root, database_url)
        self.negocial_tools = NegocialToolBuilderService(self.negocial)
        self.alpha_ho = AlphaHonorariosService(database_url, data_dir)
        self.production_analytics = ProductionAnalyticsService(self.negocial)
        self.defasagem = DefasagemService()
        self.service = NegotiadorService(self.repo, self.reader, self.negocial)
        self.overview = OverviewService(self.repo, self.service.events, self.service.overview_builder)
        self.service.events.on_created = self.overview.clear_cache
        self.parecer = ParecerService(data_dir, self.negocial)
        self.protocolo = ProtocoloService(self.repo, data_dir)
        self.colchao = ColchaoService(data_dir, self.repo)
        self.notifications = NotificationService(
            self.repo, self.service, self.parecer, self.protocolo, self.overview, self.negocial_tools
        )
        self.main_hub = MainHubService(self.overview, self.parecer, self.protocolo, self.negocial_tools)
        self.backups = BackupRetentionService(data_dir)
        self.database_maintenance = DatabaseMaintenanceService(database_url)
        self.database_monitoring = DatabaseMonitoringService(database_url, self.repo.pool_stats)
        self.database_backups = DatabaseBackupService(database_url, data_dir)
        self.attachment_storage = AttachmentStorageService()
        self.backup_retention_status = self._cleanup_backups()
        self.maintenance_scheduler = MaintenanceScheduler()
        self._schedule_maintenance()
        self.optimizer = BackgroundOptimizer(self.parecer, self.colchao, self.protocolo)
        self.database_maintenance_status = self._run_database_maintenance(dry_run=True)
        self._database_maintenance_stop = threading.Event()
        self._database_maintenance_thread = threading.Thread(
            target=self._database_maintenance_loop,
            daemon=True,
            name="database-maintenance",
        )
        self._database_maintenance_thread.start()
        self.monitor = FileMonitor(self.service, interval_seconds=30)
        self.monitor.start()
        self.optimizer.refresh_all()

    def _schedule_maintenance(self) -> None:
        backup_hours = max(1, int(os.environ.get("NEGOCIADORES_BACKUP_INTERVAL_HOURS", "24")))
        initial_delay = max(60, int(os.environ.get("NEGOCIADORES_BACKUP_INITIAL_DELAY_SECONDS", "300")))
        self.maintenance_scheduler.add_job(ScheduledJob(
            "database_backup", backup_hours * 60 * 60, initial_delay,
            lambda: self.database_backups.create_backup("automatico"),
        ))
        self.maintenance_scheduler.add_job(ScheduledJob(
            "backup_retention", 24 * 60 * 60, initial_delay + 300, self._cleanup_backups,
        ))
        monitoring_interval = max(60, int(os.environ.get("GERENCIAL_DB_MONITOR_INTERVAL_SECONDS", "300")))
        self.maintenance_scheduler.add_job(ScheduledJob(
            "database_monitoring", monitoring_interval, max(30, min(initial_delay, 60)),
            self.database_monitoring.collect,
        ))
        self.maintenance_scheduler.add_job(ScheduledJob(
            "alpha_ho_conference",
            max(60, int(os.environ.get("ALPHA_HO_RECALCULATE_SECONDS", "120"))),
            45,
            self.alpha_ho.recalculate_active,
        ))
        self.maintenance_scheduler.add_job(ScheduledJob(
            "dynamic_tool_trash",
            max(300, int(os.environ.get("DYNAMIC_TOOL_TRASH_INTERVAL_SECONDS", "300"))),
            90,
            self.negocial_tools.purge_expired_tools,
        ))

    def _cleanup_backups(self) -> dict:
        try:
            return self.backups.cleanup()
        except Exception as exc:  # Service boundary: a retention failure cannot stop startup.
            logger.exception("Falha ao aplicar retencao de backups")
            return {"ok": False, "error": str(exc)}

    def _run_database_maintenance(self, dry_run: bool = True) -> dict:
        try:
            return self.database_maintenance.cleanup({
                "dry_run": dry_run,
                "snapshot_retention_days": 120,
                "snapshot_delete_limit": 5000,
                "read_retention_days": 180,
                "session_retention_days": 7,
            })
        except Exception as exc:  # Service boundary: maintenance is observable and retried later.
            logger.exception("Falha na manutencao periodica do banco")
            return {"ok": False, "error": str(exc), "dry_run": dry_run}

    def _database_maintenance_loop(self) -> None:
        while not self._database_maintenance_stop.wait(24 * 60 * 60):
            self.database_maintenance_status = self._run_database_maintenance(dry_run=False)
