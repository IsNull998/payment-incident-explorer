from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
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


def parse_timestamp(value):
    """Convert an ISO-8601 timestamp string into a datetime object."""
    if not value or not isinstance(value, str):
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_payment_failure(payment):
    return payment.get("status") in {"PENDING", "DECLINED"}


def is_webhook_failure(payment):
    return payment.get("webhook_status") in {"FAILED", "NOT_SENT"}


def is_combined_abnormal(payment):
    """
    Combined abnormal signal:
    payment is PENDING/DECLINED AND webhook is FAILED/NOT_SENT.
    """
    return is_payment_failure(payment) and is_webhook_failure(payment)


def detect_incidents(payments, window_minutes=60):
    """
    MVP incident detector.

    A provider is marked suspicious when at least two combined abnormal
    transactions occur within a rolling 60-minute period, and the window
    also contains at least one of these supporting signals:

    - PROVIDER_TIMEOUT
    - payment failure rate >= 50%
    - webhook failure rate >= 50%

    This is intentionally simple and explainable for a time-boxed challenge.
    """
    payments_by_provider = defaultdict(list)

    for payment in payments:
        provider = payment.get("provider")
        timestamp = parse_timestamp(payment.get("created_at"))

        if not provider or timestamp is None:
            continue

        enriched = dict(payment)
        enriched["_parsed_time"] = timestamp
        payments_by_provider[provider].append(enriched)

    incidents = []

    for provider, provider_payments in payments_by_provider.items():
        provider_payments.sort(key=lambda p: p["_parsed_time"])

        abnormal_transactions = [
            p for p in provider_payments
            if is_combined_abnormal(p)
        ]

        i = 0

        while i < len(abnormal_transactions):
            start_abnormal = abnormal_transactions[i]
            start_time = start_abnormal["_parsed_time"]
            max_end_time = start_time + timedelta(minutes=window_minutes)

            cluster = [start_abnormal]
            j = i + 1

            while (
                j < len(abnormal_transactions)
                and abnormal_transactions[j]["_parsed_time"] <= max_end_time
            ):
                cluster.append(abnormal_transactions[j])
                j += 1

            if len(cluster) >= 2:
                window_start = cluster[0]["_parsed_time"]
                window_end = cluster[-1]["_parsed_time"]

                window_transactions = [
                    p for p in provider_payments
                    if window_start <= p["_parsed_time"] <= window_end
                ]

                total = len(window_transactions)

                payment_failure_count = sum(
                    1 for p in window_transactions
                    if is_payment_failure(p)
                )

                webhook_failure_count = sum(
                    1 for p in window_transactions
                    if is_webhook_failure(p)
                )

                provider_timeout_count = sum(
                    1 for p in window_transactions
                    if p.get("decline_code") == "PROVIDER_TIMEOUT"
                )

                payment_failure_rate = (
                    round(payment_failure_count / total * 100, 1)
                    if total > 0 else 0
                )

                webhook_failure_rate = (
                    round(webhook_failure_count / total * 100, 1)
                    if total > 0 else 0
                )

                reasons = []

                if provider_timeout_count > 0:
                    reasons.append("PROVIDER_TIMEOUT detected")

                if payment_failure_rate >= 50:
                    reasons.append(
                        f"Payment failure rate is {payment_failure_rate}%"
                    )

                if webhook_failure_rate >= 50:
                    reasons.append(
                        f"Webhook failure rate is {webhook_failure_rate}%"
                    )

                # Severity is intentionally conservative:
                # HIGH requires a concrete provider-timeout signal.
                # MEDIUM is a statistical anomaly that still needs human review.
                severity = None

                if provider_timeout_count > 0:
                    severity = "HIGH"
                elif (
                    payment_failure_rate >= 50
                    and webhook_failure_rate >= 50
                ):
                    severity = "MEDIUM"

                if severity:
                    incidents.append({
                        "provider": provider,
                        "severity": severity,
                        "window_start": window_start.isoformat(),
                        "window_end": window_end.isoformat(),
                        "affected_transactions": len(cluster),
                        "payment_ids": [
                            p.get("payment_id")
                            for p in cluster
                        ],
                        "provider_timeout_count": provider_timeout_count,
                        "payment_failure_rate": payment_failure_rate,
                        "webhook_failure_rate": webhook_failure_rate,
                        "reason": [
                            (
                                f"{len(cluster)} combined abnormal transactions "
                                f"detected within {window_minutes} minutes"
                            ),
                            *reasons,
                        ],
                    })

                    # Skip transactions already included in this detected cluster.
                    i = j
                    continue

            i += 1

    return incidents


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


@app.get("/api/incidents")
def get_incidents():
    payments = load_payments()
    incidents = detect_incidents(payments)

    return {
        "count": len(incidents),
        "items": incidents,
    }
