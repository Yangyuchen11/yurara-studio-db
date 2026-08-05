# app_core/services/rate_service.py
import re
import logging
import httpx
from app_core.models import SystemSetting

logger = logging.getLogger(__name__)

DEFAULT_RATES = {"JPY": 0.048}

def get_all_rates() -> dict[str, float]:
    """
    DB から全通貨の対 CNY 為替レートを取得（1単位外貨に対する CNY 値）。
    """
    rates = dict(DEFAULT_RATES)
    try:
        settings = SystemSetting.objects.filter(key__startswith="rate_CNY_per_")
        for s in settings:
            parts = s.key.split("_")
            if len(parts) >= 5:
                currency_code = parts[3]
                try:
                    rate_100 = float(s.value)
                    rates[currency_code] = rate_100 / 100.0
                except (ValueError, TypeError):
                    pass
        
        # 互換性: 旧 exchange_rate キー
        if "JPY" not in rates:
            old = SystemSetting.objects.filter(key="exchange_rate").first()
            if old:
                try:
                    rates["JPY"] = float(old.value) / 100.0
                except (ValueError, TypeError):
                    pass
    except Exception as e:
        logger.error(f"Error fetching exchange rates from DB: {e}")

    return rates


def set_rate(currency: str, rate_per_100: float) -> float:
    """
    指定通貨の為替レートを設定（100単位外貨 = X CNY の形式で入力）。
    """
    currency = currency.strip().upper()
    if not currency or currency == "CNY":
        return 1.0

    if rate_per_100 < 0.0001:
        rate_per_100 = 0.0001

    key = f"rate_CNY_per_{currency}_100"
    SystemSetting.objects.update_or_create(
        key=key,
        defaults={
            "value": str(rate_per_100),
            "description": f"100 {currency} → CNY 為替レート"
        }
    )

    if currency == "JPY":
        SystemSetting.objects.update_or_create(
            key="exchange_rate",
            defaults={"value": str(rate_per_100)}
        )

    return rate_per_100 / 100.0


def remove_rate(currency: str):
    """
    通貨の為替レート設定を削除（CNY, JPY は削除不可）。
    """
    currency = currency.strip().upper()
    if currency in ("CNY", "JPY"):
        return
    key = f"rate_CNY_per_{currency}_100"
    SystemSetting.objects.filter(key=key).delete()


def fetch_live_rates_sync() -> dict[str, float]:
    """
    Google Finance からリアルタイム為替レートを同期取得し、DBに保存。
    """
    current_rates = get_all_rates()
    currencies_to_fetch = [c for c in current_rates.keys() if c != "CNY"]
    if not currencies_to_fetch:
        return {}

    updated = {}
    try:
        with httpx.Client(timeout=10.0) as client:
            for currency in currencies_to_fetch:
                try:
                    url = f"https://www.google.com/finance/quote/{currency}-CNY"
                    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                    resp = client.get(url, headers=headers, follow_redirects=True)
                    if resp.status_code == 200:
                        match = re.search(rf'([\d\.]+)\s*,\s*"\s*{currency}\s*/\s*CNY\s*"', resp.text)
                        if not match:
                            match = re.search(r'data-last-price="([\d\.]+)"', resp.text)
                        if not match:
                            match = re.search(r'class="YMlKec fxKbKc">([\d\.]+)<', resp.text)
                        if match:
                            live_rate = float(match.group(1))
                            set_rate(currency, live_rate * 100.0)
                            updated[currency] = live_rate
                except Exception as e:
                    logger.warning(f"Failed to fetch live rate for {currency}: {e}")
    except Exception as e:
        logger.error(f"Error initializing httpx client: {e}")

    return updated


async def fetch_live_rates() -> dict[str, float]:
    """
    非同期互換ラッパー。
    """
    return fetch_live_rates_sync()
