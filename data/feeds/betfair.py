"""
Betfair Exchange API client.

Authentication modes:
  1. Non-interactive (session key) — for free/starter accounts.
     Requires BETFAIR_USERNAME, BETFAIR_PASSWORD, BETFAIR_APP_KEY.
  2. Certificate-based — for automated/production accounts.
     Requires the above PLUS BETFAIR_CERT_PATH and BETFAIR_KEY_PATH
     pointing to your registered SSL client certificate.

Set BETFAIR_AUTH_MODE=cert in .env to use certificate login.
"""

import os
import logging
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── Endpoints ────────────────────────────────────────────────────────────────
BETFAIR_API_BASE        = "https://api.betfair.com/exchange/betting/rest/v1.0"
BETFAIR_ACCOUNT_BASE    = "https://api.betfair.com/exchange/account/rest/v1.0"
BETFAIR_LOGIN_URL       = "https://identitysso.betfair.com/api/login"
BETFAIR_CERT_LOGIN_URL  = "https://identitysso-cert.betfair.com/api/certlogin"
BETFAIR_LOGOUT_URL      = "https://identitysso.betfair.com/api/logout"

# ── Sport event-type IDs on Betfair Exchange ─────────────────────────────────
SPORT_EVENT_TYPE_IDS: dict[str, str] = {
    "nba":   "7522",
    "ncaab": "7522",
    "nfl":   "6423",
    "mlb":   "61420",
    "nhl":   "7524",
}


class BetfairAuthError(Exception):
    pass


class BetfairAPIError(Exception):
    pass


class BetfairClient:
    """
    Thin wrapper around the Betfair Exchange JSON REST API.
    Instantiate once, call .login(), then use freely.
    """

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        app_key: Optional[str] = None,
        session_token: Optional[str] = None,
    ):
        self.username      = username      or os.getenv("BETFAIR_USERNAME", "")
        self.password      = password      or os.getenv("BETFAIR_PASSWORD", "")
        self.app_key       = app_key       or os.getenv("BETFAIR_APP_KEY", "")
        self.session_token = session_token or os.getenv("BETFAIR_SESSION_TOKEN", "")
        self._session      = requests.Session()

    # ── Authentication ───────────────────────────────────────────────────────

    def login(self, use_cert: bool = False) -> bool:
        """
        Login and populate self.session_token.
        use_cert=True requires BETFAIR_CERT_PATH + BETFAIR_KEY_PATH env vars
        pointing to your registered client certificate files.
        """
        if use_cert or os.getenv("BETFAIR_AUTH_MODE", "").lower() == "cert":
            return self._cert_login()
        return self._session_login()

    def _session_login(self) -> bool:
        """Interactive / non-cert login (starter accounts)."""
        resp = self._session.post(
            BETFAIR_LOGIN_URL,
            data={"username": self.username, "password": self.password},
            headers={
                "X-Application":  self.app_key,
                "Content-Type":   "application/x-www-form-urlencoded",
                "Accept":         "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "SUCCESS":
            self.session_token = data["token"]
            logger.info("Betfair session login successful")
            return True
        logger.error("Betfair login failed: %s", data.get("error"))
        raise BetfairAuthError(f"Login failed: {data.get('error')}")

    def _cert_login(self) -> bool:
        """Certificate-based non-interactive login (production accounts)."""
        cert_path = os.getenv("BETFAIR_CERT_PATH", "")
        key_path  = os.getenv("BETFAIR_KEY_PATH", "")
        if not cert_path or not key_path:
            raise BetfairAuthError(
                "BETFAIR_CERT_PATH and BETFAIR_KEY_PATH must be set for certificate login"
            )
        resp = self._session.post(
            BETFAIR_CERT_LOGIN_URL,
            data={"username": self.username, "password": self.password},
            cert=(cert_path, key_path),
            headers={
                "X-Application": self.app_key,
                "Content-Type":  "application/x-www-form-urlencoded",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("loginStatus") == "SUCCESS":
            self.session_token = data["sessionToken"]
            logger.info("Betfair certificate login successful")
            return True
        logger.error("Betfair cert login failed: %s", data.get("loginStatus"))
        raise BetfairAuthError(f"Certificate login failed: {data.get('loginStatus')}")

    def logout(self) -> None:
        try:
            self._session.post(
                BETFAIR_LOGOUT_URL,
                headers={"X-Application": self.app_key, "X-Authentication": self.session_token},
            )
        except Exception:
            pass

    def is_configured(self) -> bool:
        """True if credentials are present."""
        return bool(self.app_key and (self.session_token or (self.username and self.password)))

    # ── Internal helpers ─────────────────────────────────────────────────────

    @property
    def _headers(self) -> dict:
        return {
            "X-Application":  self.app_key,
            "X-Authentication": self.session_token,
            "Content-Type":   "application/json",
            "Accept":         "application/json",
        }

    def _betting_post(self, endpoint: str, body: dict) -> dict | list:
        url  = f"{BETFAIR_API_BASE}/{endpoint}/"
        resp = self._session.post(url, json=body, headers=self._headers)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "detail" in data:
            raise BetfairAPIError(f"{endpoint}: {data['detail']}")
        return data

    def _account_post(self, endpoint: str, body: dict) -> dict:
        url  = f"{BETFAIR_ACCOUNT_BASE}/{endpoint}/"
        resp = self._session.post(url, json=body, headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    # ── Account ──────────────────────────────────────────────────────────────

    def get_balance(self) -> dict:
        """Return account available funds."""
        data = self._account_post("getAccountFunds", {"filter": {}})
        return {
            "available_to_bet":    data.get("availableToBetBalance", 0.0),
            "exposure":            data.get("exposure", 0.0),
            "retained_commission": data.get("retainedCommission", 0.0),
            "currency":            data.get("currencyCode", "GBP"),
        }

    # ── Market discovery ─────────────────────────────────────────────────────

    def list_event_types(self) -> list:
        return self._betting_post("listEventTypes", {"filter": {}})

    def list_events(self, event_type_id: str, text_query: Optional[str] = None) -> list:
        filt: dict = {"eventTypeIds": [event_type_id]}
        if text_query:
            filt["textQuery"] = text_query
        return self._betting_post("listEvents", {"filter": filt})

    def list_market_catalogue(
        self,
        event_ids: list[str],
        market_types: Optional[list[str]] = None,
        max_results: int = 50,
    ) -> list:
        filt: dict = {"eventIds": event_ids}
        if market_types:
            filt["marketTypeCodes"] = market_types
        return self._betting_post("listMarketCatalogue", {
            "filter":            filt,
            "marketProjection":  ["EVENT", "RUNNER_DESCRIPTION", "MARKET_START_TIME"],
            "maxResults":        max_results,
        })

    def list_market_book(self, market_ids: list[str], depth: int = 3) -> list:
        return self._betting_post("listMarketBook", {
            "marketIds": market_ids,
            "priceProjection": {
                "priceData": ["EX_BEST_OFFERS"],
                "exBestOffersOverrides": {"bestPricesDepth": depth},
            },
        })

    # ── Order management ─────────────────────────────────────────────────────

    def place_bet(
        self,
        market_id:    str,
        selection_id: int,
        side:         str,   # "BACK" or "LAY"
        size:         float,
        price:        float,
        customer_ref: Optional[str] = None,
    ) -> dict:
        """
        Place a single limit order.
        persistenceType=LAPSE: unmatched portion cancelled at event start.
        """
        body: dict = {
            "marketId": market_id,
            "instructions": [{
                "orderType":   "LIMIT",
                "selectionId": selection_id,
                "side":        side,
                "limitOrder": {
                    "size":            round(size, 2),
                    "price":           round(price, 2),
                    "persistenceType": "LAPSE",
                },
            }],
        }
        if customer_ref:
            body["customerRef"] = customer_ref[:32]   # Betfair max 32 chars
        return self._betting_post("placeOrders", body)

    def cancel_bet(self, market_id: str, bet_id: str) -> dict:
        return self._betting_post("cancelOrders", {
            "marketId":    market_id,
            "instructions": [{"betId": bet_id}],
        })

    def list_current_orders(self) -> list:
        data = self._betting_post("listCurrentOrders", {"orderProjection": "ALL"})
        return data.get("currentOrders", [])  # type: ignore[union-attr]

    def list_cleared_orders(self, bet_status: str = "SETTLED") -> list:
        data = self._betting_post("listClearedOrders", {"betStatus": bet_status})
        return data.get("clearedOrders", [])  # type: ignore[union-attr]
