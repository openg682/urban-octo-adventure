from datamodel import OrderDepth, TradingState, Order
from typing import List
import json
import numpy as np

class Trader:
    def run(self, state: TradingState):
        product = "KELP"
        max_pos = 50
        short_span = 10
        long_span = 50
        vol_window = 20
        volatility_threshold = 0.004  # 0.4% std dev

        order_depth = state.order_depths[product]
        if not order_depth.buy_orders or not order_depth.sell_orders:
            return {}, 1, state.traderData

        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())
        mid_price = (best_bid + best_ask) / 2

        # Load state (price history)
        history = json.loads(state.traderData) if state.traderData else {"prices": []}
        prices = history.get("prices", [])
        prices.append(mid_price)

        # Keep only needed history
        max_len = max(long_span, vol_window) + 5
        if len(prices) > max_len:
            prices = prices[-max_len:]

        orders = []
        position = state.position.get(product, 0)

        if len(prices) >= long_span:
            prices_np = np.array(prices)

            # Calculate EMAs manually
            def compute_ema(series, span):
                alpha = 2 / (span + 1)
                ema = series[0]
                for price in series[1:]:
                    ema = alpha * price + (1 - alpha) * ema
                return ema

            ema_short = compute_ema(prices_np[-short_span:], short_span)
            ema_long = compute_ema(prices_np[-long_span:], long_span)
            momentum = (prices_np[-1] - prices_np[-2]) / prices_np[-2]

            if len(prices_np) >= vol_window + 1:
                returns = np.diff(prices_np[-(vol_window+1):]) / prices_np[-(vol_window+1):-1]
                volatility = np.std(returns)
            else:
                volatility = 0

            # Trading logic
            buy_signal = ema_short > ema_long and momentum > 0 and volatility < volatility_threshold
            sell_signal = ema_short < ema_long and momentum < 0 and volatility < volatility_threshold

            if buy_signal:
                volume = min(-order_depth.sell_orders[best_ask], max_pos - position)
                if volume > 0:
                    orders.append(Order(product, best_ask, volume))

            if sell_signal:
                volume = min(order_depth.buy_orders[best_bid], position + max_pos)
                if volume > 0:
                    orders.append(Order(product, best_bid, -volume))

        # Save updated history
        traderData = json.dumps({"prices": prices})
        return {product: orders}, 1, traderData
