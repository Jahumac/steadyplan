"""Trading 212 read-only connection helpers."""

import base64
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

from app.models.integrations import TRADING212_ENV_DEMO, TRADING212_ENV_LIVE, VALID_TRADING212_ENVS


_TRADING212_BASE_URLS = {
    TRADING212_ENV_DEMO: "https://demo.trading212.com",
    TRADING212_ENV_LIVE: "https://live.trading212.com",
}


class Trading212ConnectionError(RuntimeError):
    pass


class Trading212CredentialError(RuntimeError):
    pass


def trading212_environment_options():
    return [
        {
            "key": TRADING212_ENV_LIVE,
            "label": "Live",
            "hint": "Real-money Invest or Stocks ISA account.",
        },
        {
            "key": TRADING212_ENV_DEMO,
            "label": "Demo",
            "hint": "Paper-trading environment for safe testing.",
        },
    ]


def trading212_environment_label(environment):
    environment = (environment or "").strip().lower()
    if environment == TRADING212_ENV_DEMO:
        return "Demo"
    return "Live"


def trading212_status_label(connection):
    status = (connection or {}).get("status") or "unverified"
    if status == "connected":
        return "Connected"
    if status == "error":
        return "Needs attention"
    return "No successful broker snapshot check yet"


def mask_trading212_key(api_key):
    value = (api_key or "").strip()
    if not value:
        return "—"
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}…{value[-4:]}"


def _fernet_for_app():
    secret_key = current_app.config.get("SECRET_KEY")
    if not secret_key:
        raise Trading212CredentialError("SECRET_KEY is required before broker credentials can be stored.")
    digest = hashlib.sha256(str(secret_key).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_trading212_credential(value):
    raw = (value or "").strip()
    if not raw:
        raise Trading212CredentialError("Trading 212 credentials cannot be blank.")
    return _fernet_for_app().encrypt(raw.encode("utf-8")).decode("utf-8")


def decrypt_trading212_credential(ciphertext):
    raw = (ciphertext or "").strip()
    if not raw:
        raise Trading212CredentialError("Stored Trading 212 credential is missing.")
    try:
        return _fernet_for_app().decrypt(raw.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise Trading212CredentialError(
            "Stored Trading 212 credentials can no longer be decrypted with this app secret key."
        ) from exc


def _base_url_for_environment(environment):
    env = (environment or TRADING212_ENV_LIVE).strip().lower()
    if env not in VALID_TRADING212_ENVS:
        raise Trading212ConnectionError("Choose a valid Trading 212 environment.")
    return _TRADING212_BASE_URLS[env], env


def _authorization_header(api_key, api_secret):
    credentials = f"{(api_key or '').strip()}:{(api_secret or '').strip()}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


def _read_json_response(resp):
    body = resp.read(1024 * 1024)
    return json.loads(body.decode("utf-8"))


def _request_json(path, *, api_key, api_secret, environment, timeout=12):
    base_url, env = _base_url_for_environment(environment)
    req = urllib.request.Request(
        f"{base_url}{path}",
        headers={
            "Authorization": _authorization_header(api_key, api_secret),
            "Accept": "application/json",
            "User-Agent": "SteadyPlan/1.0 (+self-hosted read-only Trading212 integration)",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = _read_json_response(resp)
            return data, env
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        raise Trading212ConnectionError(_friendly_http_error(exc.code, body, environment=env)) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise Trading212ConnectionError(f"Trading 212 connection failed: {reason}") from exc


def _friendly_http_error(status_code, body, *, environment):
    parsed_message = None
    if body:
        try:
            payload = json.loads(body)
            parsed_message = payload.get("message") or payload.get("error") or payload.get("detail")
        except Exception:
            parsed_message = body.strip()[:200]
    if status_code == 401:
        return "Trading 212 rejected the API key pair. Check the key, secret, and environment."
    if status_code == 403:
        extra = f" {parsed_message}" if parsed_message else ""
        return (
            "Trading 212 refused this request. Check IP restrictions, confirm the Public API is enabled for this account, "
            f"and remember the broker currently limits the Public API to Invest and Stocks ISA accounts.{extra}"
        )
    if status_code == 429:
        return "Trading 212 rate-limited the request. Please wait a moment and try again."
    if parsed_message:
        return f"Trading 212 returned HTTP {status_code}: {parsed_message}"
    return f"Trading 212 returned HTTP {status_code}."


def fetch_trading212_account_summary(*, api_key, api_secret, environment):
    data, env = _request_json(
        "/api/v0/equity/account/summary",
        api_key=api_key,
        api_secret=api_secret,
        environment=environment,
    )
    cash = data.get("cash") or {}
    investments = data.get("investments") or {}
    return {
        "environment": env,
        "account_id": str(data.get("id") or "").strip() or None,
        "currency": data.get("currency") or None,
        "available_to_trade": float(cash.get("availableToTrade") or 0),
        "cash_in_pies": float(cash.get("inPies") or 0),
        "cash_reserved_for_orders": float(cash.get("reservedForOrders") or 0),
        "investments_current_value": float(investments.get("currentValue") or 0),
        "investments_total_cost": float(investments.get("totalCost") or 0),
        "investments_unrealized_profit_loss": float(investments.get("unrealizedProfitLoss") or 0),
        "investments_realized_profit_loss": float(investments.get("realizedProfitLoss") or 0),
        "total_value": float(data.get("totalValue") or 0),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _optional_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_non_blank(*values):
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _normalise_trading212_position(row):
    instrument = row.get("instrument") or {}
    ticker = _first_non_blank(
        row.get("ticker"),
        instrument.get("ticker"),
        instrument.get("symbol"),
        instrument.get("isin"),
        instrument.get("figi"),
    )
    name = _first_non_blank(
        row.get("name"),
        instrument.get("name"),
        instrument.get("shortName"),
        ticker,
        "Unnamed position",
    )
    quantity = _optional_float(row.get("quantity"))
    current_price = _optional_float(row.get("currentPrice"))
    average_price_paid = _optional_float(row.get("averagePricePaid"))
    market_value = _optional_float(row.get("marketValue") or row.get("currentValue") or row.get("positionValue"))
    if market_value is None and quantity is not None and current_price is not None:
        market_value = round(quantity * current_price, 2)
    return {
        "ticker": ticker or "",
        "name": name or "Unnamed position",
        "units": quantity,
        "price": current_price,
        "value": market_value,
        "average_price_paid": average_price_paid,
        "opened_at": row.get("createdAt") or None,
        "quantity_available_for_trading": _optional_float(row.get("quantityAvailableForTrading")),
        "quantity_in_pies": _optional_float(row.get("quantityInPies")),
        "currency": _first_non_blank(
            row.get("currency"),
            instrument.get("currencyCode"),
            instrument.get("currency"),
        ),
        "instrument": instrument,
    }


def fetch_trading212_positions(*, api_key, api_secret, environment):
    data, env = _request_json(
        "/api/v0/equity/positions",
        api_key=api_key,
        api_secret=api_secret,
        environment=environment,
    )
    if not isinstance(data, list):
        raise Trading212ConnectionError("Trading 212 returned an unexpected positions response.")
    positions = [_normalise_trading212_position(row or {}) for row in data]
    positions.sort(key=lambda row: ((row.get("name") or "").lower(), (row.get("ticker") or "").lower()))
    return {
        "environment": env,
        "positions": positions,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_trading212_portfolio_snapshot(*, api_key, api_secret, environment):
    summary = fetch_trading212_account_summary(
        api_key=api_key,
        api_secret=api_secret,
        environment=environment,
    )
    positions_payload = fetch_trading212_positions(
        api_key=api_key,
        api_secret=api_secret,
        environment=environment,
    )
    return {
        "environment": summary["environment"],
        "summary": summary,
        "positions": positions_payload["positions"],
        "fetched_at": positions_payload["fetched_at"],
    }


def probe_trading212_connection(*, api_key, api_secret, environment):
    summary = fetch_trading212_account_summary(
        api_key=api_key,
        api_secret=api_secret,
        environment=environment,
    )
    return {
        "ok": True,
        "message": (
            f"Connected to Trading 212 {trading212_environment_label(summary['environment']).lower()} account"
            f" {summary['account_id'] or '—'} ({summary['currency'] or 'unknown currency'})."
        ),
        "summary": summary,
    }
