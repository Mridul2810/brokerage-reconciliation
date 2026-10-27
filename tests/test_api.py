import unittest
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient
from psycopg import OperationalError

from brokerage.api import app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_health_is_liveness_without_database_access(self):
        with patch("brokerage.api.get_balance") as balance:
            response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        balance.assert_not_called()

    def test_balance_preserves_decimal_money_as_text(self):
        with patch("brokerage.api.get_balance", return_value=Decimal("1024.00")) as balance:
            response = self.client.get("/accounts/alex_cash/balance")
        balance.assert_called_once_with("alex_cash")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"account": "alex_cash", "currency": "USD", "balance_usd": "1024.00"})

    def test_dashboard_and_script_are_served_locally(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Operations overview", response.text)
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)

    def test_summary_returns_exact_cash_and_positions(self):
        summary = {"account": "alex_cash", "currency": "USD", "available_usd": "1024.00",
                   "reserved_usd": "100.00", "total_cash_usd": "1124.00", "positions": []}
        with patch("brokerage.api.account_summary", return_value=summary) as read:
            response = self.client.get("/accounts/alex_cash/summary")
        read.assert_called_once_with("alex_cash")
        self.assertEqual(response.json(), summary)

    def test_summary_unknown_account_returns_404(self):
        with patch("brokerage.api.account_summary", side_effect=ValueError("Unknown ledger account")):
            self.assertEqual(self.client.get("/accounts/missing/summary").status_code, 404)

    def test_run_list_requires_and_passes_account_scope(self):
        with patch("brokerage.api.list_reports", return_value=[]) as reports:
            self.assertEqual(self.client.get("/reconciliation/runs").status_code, 422)
            response = self.client.get("/reconciliation/runs?account=alex_cash")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        reports.assert_called_once_with("alex_cash")

    def test_unknown_account_returns_404(self):
        with patch("brokerage.api.get_balance", side_effect=ValueError("Unknown ledger account")):
            self.assertEqual(self.client.get("/accounts/missing/balance").status_code, 404)

    def test_saved_report_exposes_evidence_and_break_status(self):
        trade = dict(reference="fill-001", account="alex_cash", symbol="AAPL",
                     quantity=2, price_cents=4800, settlement_status="settled")
        report = dict(run_id=1, account_code="alex_cash", clearing_source="faulty.csv",
                      clearing_records_sha256="a" * 64, created_at="2026-10-27T12:00:00Z",
                      internal_records=[trade], clearing_records=[dict(trade, quantity=3)],
                      breaks=[dict(break_id=1, reference="fill-001", kind="field_mismatch",
                                   field="quantity", internal_value="2", clearing_value="3",
                                   status="open", history=[])])
        with patch("brokerage.api.get_report", return_value=report):
            response = self.client.get("/reconciliation/runs/1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["breaks"][0]["internal_value"], "2")
        self.assertEqual(response.json()["clearing_records"][0]["quantity"], 3)

    def test_unknown_report_returns_404(self):
        with patch("brokerage.api.get_report", return_value=None):
            self.assertEqual(self.client.get("/reconciliation/runs/999").status_code, 404)

    def test_invalid_report_id_is_rejected_before_query(self):
        with patch("brokerage.api.get_report") as report:
            self.assertEqual(self.client.get("/reconciliation/runs/0").status_code, 422)
        report.assert_not_called()

    def test_database_connection_error_returns_safe_503(self):
        with patch("brokerage.api.get_report", side_effect=OperationalError("private connection details")):
            response = self.client.get("/reconciliation/runs/1")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Database unavailable"})
