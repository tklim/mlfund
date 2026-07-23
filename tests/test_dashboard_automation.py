from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DashboardAutomationScriptTests(unittest.TestCase):
    def test_snapshot_sync_emits_structured_results(self):
        script = (ROOT / "scripts" / "sync_dashboard_snapshot.ps1").read_text(encoding="utf-8")
        self.assertIn("[string]$ResultPath", script)
        self.assertIn("function Write-SyncResult", script)
        self.assertIn('status = "unchanged"', script)
        self.assertIn('status = "changed"', script)
        self.assertIn("snapshot_commit", script)

    def test_daily_publisher_keeps_credentials_ephemeral_and_waits_for_deployment(self):
        script = (ROOT / "scripts" / "publish_daily_dashboard.ps1").read_text(encoding="utf-8")
        self.assertIn('Invoke-Checked -Command "python" -Arguments @("scripts/operate.py", "daily")', script)
        self.assertIn("sync_dashboard_snapshot.ps1", script)
        self.assertIn("git credential fill", script)
        self.assertIn("Wait-ForChecks", script)
        self.assertIn("Confirm-ProductionDeployment", script)
        self.assertIn("Restore-DashboardMain", script)
        self.assertIn('switch main', script)
        self.assertNotIn("token=", script.lower())

    def test_scheduler_installer_uses_publisher_with_safe_task_settings(self):
        script = (ROOT / "scripts" / "install_daily_publish_scheduler.ps1").read_text(encoding="utf-8")
        self.assertIn("publish_daily_dashboard.ps1", script)
        self.assertIn("-MultipleInstances IgnoreNew", script)
        self.assertIn("-StartWhenAvailable", script)
        self.assertIn("-ExecutionTimeLimit (New-TimeSpan -Hours 72)", script)


if __name__ == "__main__":
    unittest.main()
