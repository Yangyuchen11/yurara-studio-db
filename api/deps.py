"""
Yurara Studio REST API Gateway dependencies:
- Auth token generation & verification (shared with AuthState)
- Dynamic DB Session routing (Production PostgreSQL vs Test SQLite via X-Test-Mode header)
- Exchange rates loader
"""
import os
import hashlib
from typing import Dict, Generator, Optional
from dotenv import load_dotenv
from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

# Ensure environment variables from .env are loaded for standalone API or sub-app workers
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from models import SystemSetting


def _generate_token(username: str, password: str) -> str:
    salt = "yurara_secret_salt_2024"
    return hashlib.sha256(f"{username}{password}{salt}".encode()).hexdigest()


def get_cached_engine(is_test: bool):
    from yurara_app.state.app_state import get_cached_engine as _get_eng
    return _get_eng(is_test)


def get_allowed_users() -> Dict[str, str]:
    """Reads allowed user credentials from environment variables (matching AuthState.login)."""
    users: Dict[str, str] = {}
    creds_raw = os.getenv("APP_CREDENTIALS", "")
    if creds_raw:
        for pair in creds_raw.split(","):
            pair = pair.strip()
            if ":" in pair:
                u, p = pair.split(":", 1)
                users[u.strip()] = p.strip()
    if not users:
        admin_user = os.getenv("ADMIN_USERNAME", os.getenv("ADMIN_USER", "admin")).strip()
        admin_pass = os.getenv("ADMIN_PASSWORD", os.getenv("ADMIN_PW", "admin")).strip()
        users[admin_user] = admin_pass
    return users


def verify_auth_token(authorization: Optional[str] = Header(None)) -> str:
    """Verifies Bearer token against configured users and returns the username."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录或登录凭证缺失")
    token = authorization.replace("Bearer ", "").strip()
    users = get_allowed_users()
    for uname, pwd in users.items():
        if _generate_token(uname, pwd) == token:
            return uname
    raise HTTPException(status_code=401, detail="登录凭证已失效，请重新登录")


def is_test_mode_header(x_test_mode: Optional[str] = Header("false")) -> bool:
    """Parses the X-Test-Mode header."""
    if not x_test_mode:
        return False
    return x_test_mode.strip().lower() in ("true", "1", "yes")


def get_db_session(is_test: bool = Depends(is_test_mode_header)) -> Generator[Session, None, None]:
    """Yields a SQLAlchemy Session connected to either Prod DB or Test Sandbox SQLite DB."""
    engine = get_cached_engine(is_test)
    db = Session(bind=engine)
    try:
        yield db
    finally:
        db.close()


def load_rates_map(db: Session) -> Dict[str, float]:
    """Loads exchange rates map {currency: rate_per_1_unit} from SystemSetting."""
    rates_map: Dict[str, float] = {"CNY": 1.0}
    rate_records = db.query(SystemSetting).filter(
        SystemSetting.key.like("rate_CNY_per_%_100")
    ).all()
    for r in rate_records:
        curr = r.key.replace("rate_CNY_per_", "").replace("_100", "")
        try:
            val = float(r.value)
            if val > 0:
                rates_map[curr] = val / 100.0
        except (ValueError, TypeError):
            pass

    if "JPY" not in rates_map:
        old_jpy = db.query(SystemSetting).filter(SystemSetting.key == "exchange_rate").first()
        if old_jpy:
            try:
                val = float(old_jpy.value)
                rates_map["JPY"] = val if val < 1.0 else (val / 100.0)
            except (ValueError, TypeError):
                rates_map["JPY"] = 0.048
        else:
            rates_map["JPY"] = 0.048

    return rates_map


def format_currency(amount: float, currency: str = "CNY") -> str:
    curr = (currency or "CNY").upper()
    if curr == "JPY":
        return f"JPY {amount:,.0f}"
    if curr == "CNY":
        return f"¥ {amount:,.2f}"
    return f"{curr} {amount:,.2f}"
