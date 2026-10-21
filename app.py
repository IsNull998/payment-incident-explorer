from pathlib import Path
import json

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "yuno_mock_payments.json"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Payment Incident Explorer")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def load_payments():
    """Load payment data safely from the local JSON file."""
    if not DATA_FILE.exists():
        return []

    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            return []

        return data
    except (json.JSONDecodeError, OSError):
        return []


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/payments")
def get_payments(
    merchant: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    status: str | None = Query(default=None),
    webhook_status: str | None = Query(default=None),
):
    payments = load_payments()

    def matches(payment: dict) -> bool:
        if merchant and payment.get("merchant_id") != merchant:
            return False
        if provider and payment.get("provider") != provider:
            return False
        if status and payment.get("status") != status:
            return False
        if webhook_status and payment.get("webhook_status") != webhook_status:
            return False
        return True

    filtered = [p for p in payments if matches(p)]

    return {
        "count": len(filtered),
        "items": filtered,
    }


@app.get("/api/summary")
def get_summary():
    payments = load_payments()

    total = len(payments)

    success = sum(
        1 for p in payments
        if p.get("status") == "SUCCESS"
    )

    declined = sum(
        1 for p in payments
        if p.get("status") == "DECLINED"
    )

    pending = sum(
        1 for p in payments
        if p.get("status") == "PENDING"
    )

    webhook_delivered = sum(
        1 for p in payments
        if p.get("webhook_status") == "DELIVERED"
    )

    webhook_failed = sum(
        1 for p in payments
        if p.get("webhook_status") == "FAILED"
    )

    webhook_not_sent = sum(
        1 for p in payments
        if p.get("webhook_status") == "NOT_SENT"
    )

    failure_count = declined + pending

    failure_rate = (
        round(failure_count / total * 100, 1)
        if total > 0
        else 0
    )

    return {
        "total": total,
        "success": success,
        "declined": declined,
        "pending": pending,
        "failure_rate": failure_rate,
        "webhook_delivered": webhook_delivered,
        "webhook_failed": webhook_failed,
        "webhook_not_sent": webhook_not_sent,
    }
