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
        "take_width": 0.001,
        "clear_width": 0.5,
        "disregard_edge": 0.01,
        "join_edge": 0.001,
        "default_edge": 0.001,
        "soft_position_limit": 50,
    },
    Product.KELP: {
        "fair_value": 2030,
        "take_width": 15,
        "clear_width": 5,
        "disregard_edge": 25,
        "join_edge": 10,
        "default_edge": 15,
        "soft_position_limit": 40,
    },
    Product.SQUID_INK: {
        "fair_value": 1968,
        "take_width": 25,
        "clear_width": 20,
        "disregard_edge": 100,
        "join_edge": 20,
        "default_edge": 35,
        "soft_position_limit": 45,
    },
}

class Trader:
    def __init__(self):
        self.params = PARAMS
        self.LIMIT = {p: 50 for p in PARAMS}
        self.max_drawdown = -500
        self.capital_stop_limit = 30000
        self.max_profit_limit = 2500
        self.mid_price_history = {product: [] for product in PARAMS}
        self.window = 10
        self.default_min_spread = 1

    def take_best_orders(self, product, fair_value, take_width, orders, order_depth, position):
        position_limit = self.LIMIT[product]
        buy_volume = sell_volume = 0

        if abs(position) >= position_limit:
            return 0, 0

        if order_depth.sell_orders:
            best_ask = min(order_depth.sell_orders)
            ask_volume = -order_depth.sell_orders[best_ask]
            if best_ask <= fair_value - take_width:
                qty = min(ask_volume, position_limit - position)
                if qty > 0:
                    orders.append(Order(product, best_ask, qty))
                    buy_volume += qty

        if order_depth.buy_orders:
            best_bid = max(order_depth.buy_orders)
            bid_volume = order_depth.buy_orders[best_bid]
            if best_bid >= fair_value + take_width:
                qty = min(bid_volume, position_limit + position)
                if qty > 0:
                    orders.append(Order(product, best_bid, -qty))
                    sell_volume += qty

        return buy_volume, sell_volume

    def market_make(self, product, orders, bid, ask, position, buy_volume, sell_volume, order_depth):
        # Remove the conditional check for min_spread for RAINFOREST_RESIN only
        if product != Product.RAINFOREST_RESIN:
            min_spread = self.default_min_spread
            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid = max(order_depth.buy_orders)
                best_ask = min(order_depth.sell_orders)
                if best_ask - best_bid < min_spread:
                    return buy_volume, sell_volume  # skip market making for tight spreads (non-resin)

        # Always market make for RAINFOREST_RESIN if not hard capped
        buy_qty = self.LIMIT[product] - (position + buy_volume)
        if buy_qty > 0:
            orders.append(Order(product, bid, buy_qty))

        sell_qty = self.LIMIT[product] + (position - sell_volume)
        if sell_qty > 0:
            orders.append(Order(product, ask, -sell_qty))

        return buy_volume, sell_volume

    def clear_position(self, product, fair_value, width, orders, order_depth, position):
        buy_volume = sell_volume = 0
        fair_bid = round(fair_value - width, 2)
        fair_ask = round(fair_value + width, 2)

        if position > 0:
            clear_qty = sum(vol for price, vol in order_depth.buy_orders.items() if price >= fair_ask)
            clear_qty = min(clear_qty, position)
            if clear_qty > 0:
                orders.append(Order(product, fair_ask, -clear_qty))
                sell_volume += clear_qty

        elif position < 0:
            clear_qty = sum(-vol for price, vol in order_depth.sell_orders.items() if price <= fair_bid)
            clear_qty = min(clear_qty, -position)
            if clear_qty > 0:
                orders.append(Order(product, fair_bid, clear_qty))
                buy_volume += clear_qty

        return buy_volume, sell_volume

    def make_orders(self, product, order_depth, fair_value, position, buy_volume, sell_volume, disregard_edge, join_edge, default_edge, manage_position, soft_position_limit):
        orders = []
        asks = [p for p in order_depth.sell_orders if p > fair_value + disregard_edge]
        bids = [p for p in order_depth.buy_orders if p < fair_value - disregard_edge]

        ask = round(fair_value + default_edge, 2)
        if asks:
            best_ask = min(asks)
            ask = best_ask if abs(best_ask - fair_value) <= join_edge else best_ask - 1

        bid = round(fair_value - default_edge, 2)
        if bids:
            best_bid = max(bids)
            bid = best_bid if abs(fair_value - best_bid) <= join_edge else best_bid + 1

        if manage_position and product != Product.RAINFOREST_RESIN:
            if position > soft_position_limit:
                ask -= 1
            elif position < -soft_position_limit:
                bid += 1

        return self.market_make(product, orders, bid, ask, position, buy_volume, sell_volume, order_depth)

    def run(self, state: TradingState):
        result = {}
        traderObject = jsonpickle.decode(state.traderData) if state.traderData else {}
        capital = traderObject.get("capital", 0)
        initial_capital = traderObject.get("initial_capital", capital)

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
                
                # Make fair value dynamic for both SQUID_INK and KELP
                if product == Product.KELP:
                    dynamic_fair_value = np.mean(self.mid_price_history[product]) if len(self.mid_price_history[product]) >= 2 else p["fair_value"]
                    fair_value = dynamic_fair_value
                elif product == Product.SQUID_INK:
                    dynamic_fair_value = np.mean(self.mid_price_history[product]) if len(self.mid_price_history[product]) >= 2 else p["fair_value"]
                    fair_value = dynamic_fair_value
                else:
                    fair_value = p["fair_value"]  # For RAINFOREST_RESIN, keep static fair value

            else:
                dynamic_take_width = p["take_width"]
                fair_value = p["fair_value"]

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

            if stop_trading:
                b, s = self.clear_position(product, fair_value, p["clear_width"], orders, order_depth, position)
                buy_volume += b
                sell_volume += s

            result[product] = orders

        capital += 10
        traderObject["capital"] = capital
        traderData = jsonpickle.encode(traderObject)
        conversions = 1

        return result, conversions, traderData
