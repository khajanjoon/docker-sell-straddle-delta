import time
import requests
from datetime import datetime, timedelta, timezone

from delta_rest_client import (
    DeltaRestClient,
    create_order_format,
    round_by_tick_size
)

# ================= CONFIG =================
API_KEY = "TcwdPNNYGjjgkRW4BRIAnjL7z5TLyJ"
API_SECRET = "B5ALo5Mh8mgUREB6oGD4oyX3y185oElaz1LoU6Y3X5ZX0s8TvFZcX4YTVToJ"

STRIKE_INTERVAL = 200
CHECK_INTERVAL = 5          # seconds
ORDER_SIZE = 1
ENTRY_OFFSET = 100           # mark_price - 100
TARGET_MULTIPLIER = 0.5
MIN_MARK_PRICE = 1000        # ✅ NEW CONDITION

SEARCH_URL = "https://api.india.delta.exchange/v2/products/universal_search/mv"
BASE_URL = "https://api.india.delta.exchange"
# ==========================================

delta_client = DeltaRestClient(
    base_url=BASE_URL,
    api_key=API_KEY,
    api_secret=API_SECRET
)

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0"
}

IST = timezone(timedelta(hours=5, minutes=30))


# ---------- HELPERS ----------

def get_expiry():
    now = datetime.now(IST)
    if now.hour > 17 or (now.hour == 17 and now.minute >= 30):
        expiry_date = now.date() + timedelta(days=1)
    else:
        expiry_date = now.date()
    return expiry_date.strftime("%d%m%y")


def get_atm_strike(spot):
    return int(round(spot / STRIKE_INTERVAL) * STRIKE_INTERVAL)


def fetch_mv_products():
    r = requests.get(SEARCH_URL, headers=HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()
    return {
        p["symbol"]: p["product_id"]
        for p in data["result"]["move_options"]["products"]
        if p["underlying_asset_symbol"] == "BTC"
    }


def already_in_position(product_id):
    pos = delta_client.get_position(product_id)
    if not pos or float(pos.get("size", 0)) == 0:
        return False
    return True


# ---------- MAIN LOOP ----------

print("🚀 Auto MV Straddle Bot Started")

while True:
    try:
        expiry = get_expiry()

        btc = delta_client.get_ticker("BTCUSD")
        spot = float(btc["spot_price"])
        atm = get_atm_strike(spot)

        strikes = [atm, atm + 200, atm - 200, atm + 400, atm - 400]
        mv_products = fetch_mv_products()

        selected_symbol = None
        selected_product_id = None

        for strike in strikes:
            symbol = f"MV-BTC-{strike}-{expiry}"
            if symbol in mv_products:
                selected_symbol = symbol
                selected_product_id = mv_products[symbol]
                break

        if not selected_symbol:
            print("❌ No MV found — retrying")
            time.sleep(CHECK_INTERVAL)
            continue

        print(f"\n📊 Spot: {spot} | ATM: {atm} | MV: {selected_symbol}")

        if already_in_position(selected_product_id):
            print("⚠️ Position already open — skipping")
            time.sleep(CHECK_INTERVAL)
            continue

        ticker = delta_client.get_ticker(selected_symbol)
        raw_mark_price = float(ticker["mark_price"])

        # ✅ MARK PRICE CONDITION
        if raw_mark_price <= MIN_MARK_PRICE:
            print(f"⛔ Mark price {raw_mark_price} <= {MIN_MARK_PRICE} — skipping trade")
            time.sleep(CHECK_INTERVAL)
            continue

        mark_price = raw_mark_price - ENTRY_OFFSET

        target_price = round_by_tick_size(
            mark_price * TARGET_MULTIPLIER,
            tick_size=0.5
        )

        order_sell = create_order_format(
            product_id=selected_product_id,
            size=ORDER_SIZE,
            side="sell",
            price=mark_price
        )

        order_buy = create_order_format(
            product_id=selected_product_id,
            size=ORDER_SIZE,
            side="buy",
            price=target_price
        )

        delta_client.batch_create(
            selected_product_id,
            [order_sell, order_buy]
        )

        print(f"✅ Orders placed | SELL @ {mark_price} | BUY @ {target_price}")

    except Exception as e:
        print("❌ Error:", e)

    time.sleep(CHECK_INTERVAL)
