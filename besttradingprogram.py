from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import jsonpickle
import numpy as np

class Product:
    RAINFOREST_RESIN = "RAINFOREST_RESIN"
    KELP = "KELP"
    SQUID_INK = "SQUID_INK"

PARAMS = {
    Product.RAINFOREST_RESIN: {
        "fair_value": 10000,
        "spread_trade_volume": 10,
    },
    Product.KELP: {},
    Product.SQUID_INK: {},
}

class Trader:
    def __init__(self):
        self.price_history_limit = 50
        self.capital_stop_limit = 30000  # Can be made dynamic later

    def linear_regression(self, y: List[float]) -> float:
        """Simple linear regression slope of price history"""
        if len(y) < 2:
            return 0
        x = np.arange(len(y))
        slope, _ = np.polyfit(x, y, 1)
        return slope

    def run(self, state: TradingState):
        result = {}

        # Load or initialize persistent state
        traderObject = jsonpickle.decode(state.traderData) if state.traderData else {}
        capital = traderObject.get("capital", 0)
        if "price_history" not in traderObject:
            traderObject["price_history"] = {p: [] for p in PARAMS}

        price_history = traderObject["price_history"]

        for product in PARAMS:
            if product not in state.order_depths:
                continue

            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            position = state.position.get(product, 0)

            # --- Compute mid-price and update history ---
            if order_depth.sell_orders and order_depth.buy_orders:
                best_ask = min(order_depth.sell_orders)
                best_bid = max(order_depth.buy_orders)
                mid_price = (best_ask + best_bid) / 2
                price_history[product].append(mid_price)
                if len(price_history[product]) > self.price_history_limit:
                    price_history[product].pop(0)
            else:
                continue  # Skip this product if no market data

            # --- Rainbow Resin: Mean-reversion/Spread Capture ---
            if product == Product.RAINFOREST_RESIN:
                fair = PARAMS[product]["fair_value"]
                spread_trade_volume = PARAMS[product]["spread_trade_volume"]

                if best_ask - best_bid >= 2:
                    # Buy near bid, sell near ask (inside spread)
                    orders.append(Order(product, best_bid + 1, spread_trade_volume))
                    orders.append(Order(product, best_ask - 1, -spread_trade_volume))

            # --- Kelp & Squid Ink: Trend-based trading with regression ---
            elif product in [Product.KELP, Product.SQUID_INK]:
                if len(price_history[product]) >= 10:
                    slope = self.linear_regression(price_history[product])

                    trade_volume = 5
                    slope_threshold = 0.2  # Can be fine-tuned

                    if slope > slope_threshold:
                        if order_depth.sell_orders:
                            best_ask = min(order_depth.sell_orders)
                            orders.append(Order(product, best_ask, trade_volume))  # Long
                    elif slope < -slope_threshold:
                        if order_depth.buy_orders:
                            best_bid = max(order_depth.buy_orders)
                            orders.append(Order(product, best_bid, -trade_volume))  # Short

            result[product] = orders

        # --- Update capital (placeholder logic for testing) ---
        capital += 5  # This is a stand-in; replace with real PnL calc
        traderObject["capital"] = capital
        traderObject["price_history"] = price_history
        traderData = jsonpickle.encode(traderObject)

        conversions = 1
        return result, conversions, traderData
