import time
from datetime import datetime, timedelta, timezone

from delta_rest_client import (
    DeltaRestClient,
    create_order_format,
    round_by_tick_size
)

# ================= CONFIG =================
API_KEY = "TcwdPNNYGjjgkRW4BRIAnjL7z5TLyJ"
API_SECRET = "B5ALo5Mh8mgUREB6oGD4oyX3y185oElaz1LoU6Y3X5ZX0s8TvFZcX4YTVToJ"

BASE_URL = "https://api.india.delta.exchange"

STRIKE_INTERVAL = 1000
STRIKE_DISTANCE = 8000
ORDER_SIZE = 1
CHECK_INTERVAL = 5
PRICE_OFFSET = 500
MIN_MARK_PRICE = 10000     # ✅ NEW CONDITION
# =========================================

delta_client = DeltaRestClient(
    base_url=BASE_URL,
    api_key=API_KEY,
    api_secret=API_SECRET
)

IST = timezone(timedelta(hours=5, minutes=30))

# ---------- HELPERS ----------

def get_expiry():
    expiry = datetime(2026, 3, 27)
    return expiry.strftime("%d%m%y")


def get_atm_strike(spot):
    return int(round(float(spot) / STRIKE_INTERVAL) * STRIKE_INTERVAL)


def get_product_id(symbol):
    return delta_client.get_product(symbol)["id"]


def position_exists(product_id):
    pos = delta_client.get_position(product_id)
    if not pos:
        return False
    return abs(float(pos.get("size", 0))) > 0


def get_straddle_status(call_symbol, put_symbol):
    status = {"call": False, "put": False}

    try:
        status["call"] = position_exists(get_product_id(call_symbol))
    except Exception:
        pass

    try:
        status["put"] = position_exists(get_product_id(put_symbol))
    except Exception:
        pass

    return status


# ---------- MAIN ----------
print("🚀 BUY STRADDLE BOT STARTED")

while True:
    try:
        expiry = get_expiry()

        btc = delta_client.get_ticker("BTCUSD")
        spot = float(btc["spot_price"])
        atm = get_atm_strike(spot)

        call_strike = atm - STRIKE_DISTANCE
        put_strike  = atm + STRIKE_DISTANCE

        call_symbol = f"C-BTC-{call_strike}-{expiry}"
        put_symbol  = f"P-BTC-{put_strike}-{expiry}"

        print(f"\n🔁 Spot {spot} | ATM {atm}")
        print(f"📌 CALL {call_strike} | PUT {put_strike} | Expiry {expiry}")

        status = get_straddle_status(call_symbol, put_symbol)

        # -------- BUY CALL --------
        if not status["call"]:
            call_id = get_product_id(call_symbol)
            call_ticker = delta_client.get_ticker(call_symbol)
            call_mark = float(call_ticker["mark_price"])

            if call_mark >= MIN_MARK_PRICE:
                call_price = round_by_tick_size(
                    call_mark + PRICE_OFFSET, 0.5
                )

                call_order = create_order_format(
                    product_id=call_id,
                    size=ORDER_SIZE,
                    side="buy",
                    price=call_price
                )

                delta_client.batch_create(call_id, [call_order])
                print(f"✅ CALL BOUGHT | {call_symbol} @ {call_price}")
            else:
                print(f"⚠️ CALL skipped (mark {call_mark} < {MIN_MARK_PRICE})")
        else:
            print("⏭️ CALL already exists")

        # -------- BUY PUT --------
        if not status["put"]:
            put_id = get_product_id(put_symbol)
            put_ticker = delta_client.get_ticker(put_symbol)
            put_mark = float(put_ticker["mark_price"])

            if put_mark >= MIN_MARK_PRICE:
                put_price = round_by_tick_size(
                    put_mark + PRICE_OFFSET, 0.5
                )

                put_order = create_order_format(
                    product_id=put_id,
                    size=ORDER_SIZE,
                    side="buy",
                    price=put_price
                )

                delta_client.batch_create(put_id, [put_order])
                print(f"✅ PUT BOUGHT | {put_symbol} @ {put_price}")
            else:
                print(f"⚠️ PUT skipped (mark {put_mark} < {MIN_MARK_PRICE})")
        else:
            print("⏭️ PUT already exists")

    except Exception as e:
        print("❌ Error:", e)

    time.sleep(CHECK_INTERVAL)
