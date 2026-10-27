"""Local read-only API for the brokerage simulation."""

from datetime import datetime
from pathlib import Path as FilePath
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg import OperationalError
from pydantic import BaseModel

from brokerage.repository import get_balance
from brokerage.reports import get_report
from brokerage.dashboard_data import account_summary, list_reports


class BalanceResponse(BaseModel):
    account: str
    currency: Literal["USD"] = "USD"
    balance_usd: str


class TradeView(BaseModel):
    reference: str
    account: str
    symbol: str
    quantity: int
    price_cents: int
    settlement_status: Literal["pending", "settled"]


class InvestigationView(BaseModel):
    event_id: int
    reference: str
    break_id: int
    status: Literal["open", "investigating", "resolved"]
    actor: str
    note: str
    created_at: datetime


class BreakView(BaseModel):
    break_id: int
    reference: str
    kind: str
    field: str
    internal_value: str
    clearing_value: str
    status: Literal["open", "investigating", "resolved"]
    history: list[InvestigationView]


class ReportResponse(BaseModel):
    run_id: int
    account_code: str
    clearing_source: str
    clearing_records_sha256: str
    created_at: datetime
    internal_records: list[TradeView]
    clearing_records: list[TradeView]
    breaks: list[BreakView]


app = FastAPI(
    title="Brokerage Ledger & Reconciliation API",
    version="0.1.0",
    description="Local simulation: read cash balances and preserved reconciliation evidence.",
)

static_directory = FilePath(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_directory), name="static")


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(static_directory / "index.html")


@app.get("/accounts/{account_code}/summary", tags=["Accounts"])
def summary(account_code: str):
    try:
        return account_summary(account_code)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/reconciliation/runs", tags=["Reconciliation"])
def recent_reports(account: str):
    return list_reports(account)


@app.exception_handler(OperationalError)
def database_unavailable(request, error):
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


@app.get("/health", tags=["Service"])
def health():
    """Liveness only: this does not check database readiness."""
    return {"status": "ok"}


@app.get("/accounts/{account_code}/balance", response_model=BalanceResponse, tags=["Accounts"])
def account_balance(account_code: str):
    try:
        balance = get_balance(account_code)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    # Money is returned as text to avoid floating-point conversion by clients.
    return BalanceResponse(account=account_code, balance_usd=str(balance))


@app.get("/reconciliation/runs/{run_id}", response_model=ReportResponse, tags=["Reconciliation"])
def reconciliation_report(run_id: Annotated[int, Path(gt=0)]):
    report = get_report(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Reconciliation run not found")
    return report
