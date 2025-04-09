# trading_bot.py

from datamodel import OrderDepth, TradingState, Order
from typing import List
import jsonpickle
import numpy as np

class Product:
    RAINFOREST_RESIN = "RAINFOREST_RESIN"
    KELP = "KELP"
    SQUID_INK = "SQUID_INK"

PARAMS = {
    Product.RAINFOREST_RESIN: {
        "fair_value": 10000,
        "take_width": 2,
        "clear_width": 0.5,
        "disregard_edge": 3,
        "join_edge": 1,
        "default_edge": 2,
        "soft_position_limit": 25,
    },
    Product.KELP: {
        "fair_value": 2030,
        "take_width": 15,  # This will be updated dynamically
        "clear_width": 5,
        "disregard_edge": 30,
        "join_edge": 10,
        "default_edge": 20,
        "soft_position_limit": 30,
    },
    Product.SQUID_INK: {
        "fair_value": 1968,
        "take_width": 50,
        "clear_width": 20,
        "disregard_edge": 150,
        "join_edge": 20,
        "default_edge": 50,
        "soft_position_limit": 30,
    },

class Trader:
    def __init__(self):
        self.params = PARAMS
        self.LIMIT = {p: 50 for p in PARAMS}
        self.max_drawdown = -500
        self.capital_stop_limit = 500
        self.max_profit_limit = 1200  # Changed the maximum profit limit to 1200
        self.mid_price_history = {product: [] for product in PARAMS}
        self.window = 10  # window for rolling volatility
        self.min_spread = 3  # minimum spread required to market make

    def run(self, state: TradingState):
        result = {}
        traderObject = jsonpickle.decode(state.traderData) if state.traderData else {}
        capital = traderObject.get("capital", 0)
        initial_capital = traderObject.get("initial_capital", capital)  # Store initial capital

        # Check if profit limit has been reached
        profit = capital - initial_capital
        stop_trading = capital >= self.capital_stop_limit or capital <= self.max_drawdown or profit >= self.max_profit_limit

        for product in self.params:
            if product not in state.order_depths:
                continue

            orders = []
            position = state.position.get(product, 0)
            order_depth = state.order_depths[product]
            p = self.params[product]

            buy_volume = sell_volume = 0

            if order_depth.buy_orders and order_depth.sell_orders:
                mid_price = (max(order_depth.buy_orders) + min(order_depth.sell_orders)) / 2
                self.mid_price_history[product].append(mid_price)
                if len(self.mid_price_history[product]) > self.window:
                    self.mid_price_history[product].pop(0)

                volatility = np.std(self.mid_price_history[product]) if len(self.mid_price_history[product]) >= 2 else 0
                dynamic_take_width = max(10, volatility * 1.5) if product == Product.KELP else p["take_width"]
            else:
                dynamic_take_width = p["take_width"]

            fair_value = p["fair_value"]  # Keep static for now

            if not stop_trading:
                b, s = self.take_best_orders(product, fair_value, dynamic_take_width, orders, order_depth, position)
                buy_volume += b
                sell_volume += s

                b, s = self.make_orders(
                    product, order_depth, fair_value, position, buy_volume, sell_volume,
                    p["disregard_edge"], p["join_edge"], p["default_edge"], True, p["soft_position_limit"]
                )
                buy_volume += b
                sell_volume += s

            # If profit limit reached or capital stop limit, close all positions
            if stop_trading:
                b, s = self.clear_position(product, fair_value, p["clear_width"], orders, order_depth, position)
                buy_volume += b
                sell_volume += s

            result[product] = orders

        capital += 10  # Increment capital, adjust as needed
        traderObject["capital"] = capital
        traderData = jsonpickle.encode(traderObject)
        conversions = 1

        return result, conversions, traderData
