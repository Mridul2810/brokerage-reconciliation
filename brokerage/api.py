"""Local read-only API for the brokerage simulation."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import JSONResponse
from psycopg import OperationalError
from pydantic import BaseModel

from brokerage.repository import get_balance
from brokerage.reports import get_report


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
