import hashlib
import hmac
import time
import os
import requests
from urllib.parse import urlencode
from dotenv import load_dotenv
from bot.logging_config import setup_logger

load_dotenv()
logger = setup_logger()


class BinanceClientError(Exception):
    pass


class BinanceClient:
    def __init__(self):
        self.api_key    = os.getenv("BINANCE_API_KEY")
        self.api_secret = os.getenv("BINANCE_API_SECRET")
        self.base_url   = os.getenv("BINANCE_BASE_URL", "https://demo-fapi.binance.com")

        if not self.api_key or not self.api_secret:
            raise BinanceClientError(
                "API key or secret missing. Check your .env file."
            )

        self.session = requests.Session()
        self.session.headers.update({
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        })

    def _sign(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        return params

    def _safe_params_log(self, params: dict) -> dict:
        return {k: v for k, v in params.items() if k not in ("signature",)}

    def post(self, endpoint: str, params: dict) -> dict:
        signed = self._sign(params.copy())
        url    = f"{self.base_url}{endpoint}"

        logger.debug(
            f"Outgoing POST | {endpoint} | params={self._safe_params_log(signed)}"
        )

        try:
            response = self.session.post(url, data=signed, timeout=10)
            response.raise_for_status()
            data = response.json()
            logger.debug(f"Response | orderId={data.get('orderId')} status={data.get('status')}")
            return data

        except requests.exceptions.ConnectionError:
            logger.error("Network error — could not reach Binance API")
            raise BinanceClientError("Network error. Check your internet connection.")

        except requests.exceptions.Timeout:
            logger.error("Request timed out after 10s")
            raise BinanceClientError("Request timed out. Try again.")

        except requests.exceptions.HTTPError:
            error_data = {}
            try:
                error_data = response.json()
            except Exception:
                pass
            msg  = error_data.get("msg", str(response.status_code))
            code = error_data.get("code", "unknown")
            logger.error(f"Binance API error | code={code} msg={msg}")
            raise BinanceClientError(f"Binance API error [{code}]: {msg}")

    def get_price(self, symbol: str) -> float:
        url = f"{self.base_url}/fapi/v1/ticker/price"
        try:
            response = self.session.get(url, params={"symbol": symbol}, timeout=10)
            response.raise_for_status()
            data  = response.json()
            price = float(data["price"])
            logger.debug(f"Live price | symbol={symbol} price={price}")
            return price
        except Exception as e:
            logger.warning(f"Could not fetch live price for {symbol}: {e}")
            raise BinanceClientError(f"Could not fetch live price: {e}")