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

STRIKE_INTERVAL = 200
ITM_DISTANCE = 0          # 0 = ATM
ORDER_SIZE = 1
CHECK_INTERVAL = 5
PRICE_OFFSET = 100
# =========================================

delta_client = DeltaRestClient(
    base_url=BASE_URL,
    api_key=API_KEY,
    api_secret=API_SECRET
)

IST = timezone(timedelta(hours=5, minutes=30))

# ---------- STRADDLE TRACKER ----------
open_straddle = {
    "call": None,
    "put": None
}

# ---------- HELPERS ----------

def get_expiry():
    now = datetime.now(IST)
    if now.hour > 17 or (now.hour == 17 and now.minute >= 30):
        expiry = now.date() + timedelta(days=3)
    else:
        expiry = now.date() + timedelta(days=2)
    return expiry.strftime("%d%m%y")


def get_atm_strike(spot):
    return int(round(spot / STRIKE_INTERVAL) * STRIKE_INTERVAL)


def already_in_position(product_id):
    pos = delta_client.get_position(product_id)
    if not pos:
        return False
    return abs(float(pos.get("size", 0))) > 0


def get_product_id(symbol):
    product = delta_client.get_product(symbol)
    return product["id"]


def load_existing_position(symbol, product_id):
    pos = delta_client.get_position(product_id)
    print("Loaded existing position:", pos)
    if not pos:
        return None

    size = abs(float(pos.get("size", 0)))
    if size == 0:
        return None

    return {
        "symbol": symbol,
        "product_id": product_id,
        "entry_price": float(pos["entry_price"]),
        "qty": size
    }

# ---------- MAIN ----------

print("🚀 SELL STRADDLE + LIVE PnL STARTED")

while True:
    try:
        # ---------- LIVE PnL ----------
        # ---------- LIVE PnL ----------
        if open_straddle["call"] and open_straddle["put"]:
         call_ticker = delta_client.get_ticker(open_straddle["call"]["symbol"])
         put_ticker  = delta_client.get_ticker(open_straddle["put"]["symbol"])

         call_ltp = float(call_ticker["mark_price"])
         put_ltp  = float(put_ticker["mark_price"])

         call_entry = float(open_straddle["call"]["entry_price"])
         put_entry  = float(open_straddle["put"]["entry_price"])

         call_qty = float(open_straddle["call"]["qty"])
         put_qty  = float(open_straddle["put"]["qty"])

         call_pnl = (call_entry - call_ltp) * call_qty
         put_pnl  = (put_entry - put_ltp) * put_qty

         total_pnl = call_pnl + put_pnl

         print(
        f"📈 PnL | CALL: {call_pnl:.2f} | "
        f"PUT: {put_pnl:.2f} | "
        f"TOTAL: {total_pnl:.2f}"
      )


        # ---------- ENTRY / DETECTION ----------
        expiry = get_expiry()

        btc = delta_client.get_ticker("BTCUSD")
        spot = float(btc["spot_price"])
        atm = get_atm_strike(spot)

        call_strike = atm - ITM_DISTANCE
        put_strike  = atm + ITM_DISTANCE

        call_symbol = f"C-BTC-{call_strike}-{expiry}"
        put_symbol  = f"P-BTC-{put_strike}-{expiry}"

        call_id = get_product_id(call_symbol)
        put_id  = get_product_id(put_symbol)

        # ---- EXISTING STRADDLE DETECTION ----
        if already_in_position(call_id) and already_in_position(put_id):
            if not open_straddle["call"] and not open_straddle["put"]:
                open_straddle["call"] = load_existing_position(call_symbol, call_id)
                open_straddle["put"]  = load_existing_position(put_symbol, put_id)
                print("🔄 Existing STRADDLE detected — LIVE PnL enabled")

            time.sleep(CHECK_INTERVAL)
            continue

        # ---- IF STRADDLE ALREADY TRACKED, SKIP ENTRY ----
        if open_straddle["call"] or open_straddle["put"]:
            time.sleep(CHECK_INTERVAL)
            continue

        print(f"\n📊 Spot: {spot} | ATM: {atm}")
        print(f"📞 CALL: {call_symbol}")
        print(f"📉 PUT : {put_symbol}")

        call_ticker = delta_client.get_ticker(call_symbol)
        put_ticker  = delta_client.get_ticker(put_symbol)

        call_price = round_by_tick_size(float(call_ticker["mark_price"]) - PRICE_OFFSET, 0.5)
        put_price  = round_by_tick_size(float(put_ticker["mark_price"]) - PRICE_OFFSET, 0.5)

        call_order = create_order_format(
            product_id=call_id,
            size=ORDER_SIZE,
            side="sell",
            price=call_price
        )

        put_order = create_order_format(
            product_id=put_id,
            size=ORDER_SIZE,
            side="sell",
            price=put_price
        )

        delta_client.batch_create(call_id, [call_order])
        delta_client.batch_create(put_id, [put_order])

        open_straddle["call"] = {
            "symbol": call_symbol,
            "product_id": call_id,
            "entry_price": call_price,
            "qty": ORDER_SIZE
        }

        open_straddle["put"] = {
            "symbol": put_symbol,
            "product_id": put_id,
            "entry_price": put_price,
            "qty": ORDER_SIZE
        }

        print(f"✅ STRADDLE SOLD | CALL @ {call_price} | PUT @ {put_price}")

    except Exception as e:
        print("❌ Error:", e)

    time.sleep(CHECK_INTERVAL)  
