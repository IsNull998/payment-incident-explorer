# Yuno Tutorial Stage 1

This is the walking-skeleton version of the Payment Incident Explorer.

## What works

- Loads payment data from `yuno_mock_payments.json`
- Serves a web page at `/`
- Health endpoint at `/health`
- Payment API at `/api/payments`
- Basic query filters are already supported:
  - `merchant`
  - `provider`
  - `status`
  - `webhook_status`

## Run locally

```bash
python -m venv .venv
```

Windows:

```bash
.venv\\Scripts\\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start server:

```bash
uvicorn app:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

API examples:

```text
http://127.0.0.1:8000/api/payments
http://127.0.0.1:8000/api/payments?provider=AcquirerX
http://127.0.0.1:8000/api/payments?status=DECLINED
```

## Why this stage exists

The goal is not to build the final solution yet.

The goal is to prove that:

Browser -> FastAPI -> JSON data

works end to end before adding dashboard logic, filters, details, incident analysis, deployment, and README polish.
