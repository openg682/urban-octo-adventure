from datamodel import OrderDepth, TradingState, Order
from typing import List
import jsonpickle
import numpy as np

class Product:
    KELP = "KELP"
    RAINFOREST_RESIN = "RAINFOREST_RESIN"
    SQUID_INK = "SQUID_INK"

PARAMS = {
    Product.KELP: {
        "fair_value": 2020,
        "take_width": 10,
        "clear_width": 10,
        "disregard_edge": 10,
        "join_edge": 5,
        "default_edge": 10,
        "soft_position_limit": 100,
    },
    Product.RAINFOREST_RESIN: {
        "fair_value": 10000,
        "take_width": 0.001,
        "clear_width": 0.0005,
        "disregard_edge": 0.01,
        "join_edge": 0.0005,
        "default_edge": 0.001,
        "soft_position_limit": 150,
    },
    Product.SQUID_INK: {
        "fair_value": 1968,
        "take_width": 25,
        "clear_width": 10,
        "disregard_edge": 60,
        "join_edge": 20,
        "default_edge": 35,
        "soft_position_limit": 45,
    },
}

class Trader:
    def __init__(self):
        self.params = PARAMS
        self.LIMIT = {p: 100 for p in PARAMS}
        self.max_drawdown = -500
        self.capital_stop_limit = 30000
        self.max_profit_limit = 2500
        self.mid_price_history = {product: [] for product in PARAMS}
        self.window = 10
        self.default_min_spread = 1.1

    # Kelp Section
    def take_best_orders_kelp(self, fair_value, take_width, orders, order_depth, position):
        position_limit = self.LIMIT[Product.KELP]
        buy_volume = sell_volume = 0

        if abs(position) >= position_limit:
            return 0, 0

        if order_depth.sell_orders:
            best_ask = min(order_depth.sell_orders)
            ask_volume = -order_depth.sell_orders[best_ask]
            if best_ask <= fair_value - take_width:
                qty = min(ask_volume, position_limit - position)
                if qty > 0:
                    orders.append(Order(Product.KELP, best_ask, qty))
                    buy_volume += qty

        if order_depth.buy_orders:
            best_bid = max(order_depth.buy_orders)
            bid_volume = order_depth.buy_orders[best_bid]
            if best_bid >= fair_value + take_width:
                qty = min(bid_volume, position_limit + position)
                if qty > 0:
                    orders.append(Order(Product.KELP, best_bid, -qty))
                    sell_volume += qty

        return buy_volume, sell_volume

    def market_make_kelp(self, orders, bid, ask, position, buy_volume, sell_volume):
        buy_qty = self.LIMIT[Product.KELP] - (position + buy_volume)
        if buy_qty > 0:
            orders.append(Order(Product.KELP, bid, buy_qty))

        sell_qty = self.LIMIT[Product.KELP] + (position - sell_volume)
        if sell_qty > 0:
            orders.append(Order(Product.KELP, ask, -sell_qty))

        return buy_volume, sell_volume

    def make_orders_kelp(self, order_depth, fair_value, position, buy_volume, sell_volume, disregard_edge, join_edge, default_edge):
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

        return self.market_make_kelp(orders, bid, ask, position, buy_volume, sell_volume)

    # Rainforest Resin Section
    def take_best_orders_rainforest_resin(self, fair_value, take_width, orders, order_depth, position):
        position_limit = self.LIMIT[Product.RAINFOREST_RESIN]
        buy_volume = sell_volume = 0

        if abs(position) >= position_limit:
            return 0, 0

        if order_depth.sell_orders:
            best_ask = min(order_depth.sell_orders)
            ask_volume = -order_depth.sell_orders[best_ask]
            if best_ask <= fair_value - take_width:
                qty = min(ask_volume, position_limit - position)
                if qty > 0:
                    orders.append(Order(Product.RAINFOREST_RESIN, best_ask, qty))
                    buy_volume += qty

        if order_depth.buy_orders:
            best_bid = max(order_depth.buy_orders)
            bid_volume = order_depth.buy_orders[best_bid]
            if best_bid >= fair_value + take_width:
                qty = min(bid_volume, position_limit + position)
                if qty > 0:
                    orders.append(Order(Product.RAINFOREST_RESIN, best_bid, -qty))
                    sell_volume += qty

        return buy_volume, sell_volume

    def market_make_rainforest_resin(self, orders, bid, ask, position, buy_volume, sell_volume):
        buy_qty = self.LIMIT[Product.RAINFOREST_RESIN] - (position + buy_volume)
        if buy_qty > 0:
            orders.append(Order(Product.RAINFOREST_RESIN, bid, buy_qty))

        sell_qty = self.LIMIT[Product.RAINFOREST_RESIN] + (position - sell_volume)
        if sell_qty > 0:
            orders.append(Order(Product.RAINFOREST_RESIN, ask, -sell_qty))

        return buy_volume, sell_volume

    def make_orders_rainforest_resin(self, order_depth, fair_value, position, buy_volume, sell_volume, disregard_edge, join_edge, default_edge):
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

        return self.market_make_rainforest_resin(orders, bid, ask, position, buy_volume, sell_volume)

    # Squid Ink Section
    def take_best_orders_squid_ink(self, fair_value, take_width, orders, order_depth, position):
        position_limit = self.LIMIT[Product.SQUID_INK]
        buy_volume = sell_volume = 0

        if abs(position) >= position_limit:
            return 0, 0

        if order_depth.sell_orders:
            best_ask = min(order_depth.sell_orders)
            ask_volume = -order_depth.sell_orders[best_ask]
            if best_ask <= fair_value - take_width:
                qty = min(ask_volume, position_limit - position)
                if qty > 0:
                    orders.append(Order(Product.SQUID_INK, best_ask, qty))
                    buy_volume += qty

        if order_depth.buy_orders:
            best_bid = max(order_depth.buy_orders)
            bid_volume = order_depth.buy_orders[best_bid]
            if best_bid >= fair_value + take_width:
                qty = min(bid_volume, position_limit + position)
                if qty > 0:
                    orders.append(Order(Product.SQUID_INK, best_bid, -qty))
                    sell_volume += qty

        return buy_volume, sell_volume

    def market_make_squid_ink(self, orders, bid, ask, position, buy_volume, sell_volume):
        buy_qty = self.LIMIT[Product.SQUID_INK] - (position + buy_volume)
        if buy_qty > 0:
            orders.append(Order(Product.SQUID_INK, bid, buy_qty))

        sell_qty = self.LIMIT[Product.SQUID_INK] + (position - sell_volume)
        if sell_qty > 0:
            orders.append(Order(Product.SQUID_INK, ask, -sell_qty))

        return buy_volume, sell_volume

    def make_orders_squid_ink(self, order_depth, fair_value, position, buy_volume, sell_volume, disregard_edge, join_edge, default_edge):
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

        return self.market_make_squid_ink(orders, bid, ask, position, buy_volume, sell_volume)

    # Main Run Function
    def run(self, state: TradingState):
        result = {}
        traderObject = jsonpickle.decode(state.traderData) if state.traderData else {}
        capital = traderObject.get("capital", 0)
        initial_capital = traderObject.get("initial_capital", capital)

        # Kelp
        if Product.KELP in state.order_depths:
            orders = []
            order_depth = state.order_depths[Product.KELP]
            position = state.position.get(Product.KELP, 0)
            p = self.params[Product.KELP]

            buy_volume = sell_volume = 0
            fair_value = p["fair_value"]
            b, s = self.take_best_orders_kelp(fair_value, p["take_width"], orders, order_depth, position)
            buy_volume += b
            sell_volume += s

            b, s = self.make_orders_kelp(order_depth, fair_value, position, buy_volume, sell_volume, p["disregard_edge"], p["join_edge"], p["default_edge"])
            buy_volume += b
            sell_volume += s

            result[Product.KELP] = orders

        # Rainforest Resin
        if Product.RAINFOREST_RESIN in state.order_depths:
            orders = []
            order_depth = state.order_depths[Product.RAINFOREST_RESIN]
            position = state.position.get(Product.RAINFOREST_RESIN, 0)
            p = self.params[Product.RAINFOREST_RESIN]

            buy_volume = sell_volume = 0
            fair_value = p["fair_value"]
            b, s = self.take_best_orders_rainforest_resin(fair_value, p["take_width"], orders, order_depth, position)
            buy_volume += b
            sell_volume += s

            b, s = self.make_orders_rainforest_resin(order_depth, fair_value, position, buy_volume, sell_volume, p["disregard_edge"], p["join_edge"], p["default_edge"])
            buy_volume += b
            sell_volume += s

            result[Product.RAINFOREST_RESIN] = orders

        # Squid Ink
        if Product.SQUID_INK in state.order_depths:
            orders = []
            order_depth = state.order_depths[Product.SQUID_INK]
            position = state.position.get(Product.SQUID_INK, 0)
            p = self.params[Product.SQUID_INK]

            buy_volume = sell_volume = 0
            fair_value = p["fair_value"]
            b, s = self.take_best_orders_squid_ink(fair_value, p["take_width"], orders, order_depth, position)
            buy_volume += b
            sell_volume += s

            b, s = self.make_orders_squid_ink(order_depth, fair_value, position, buy_volume, sell_volume, p["disregard_edge"], p["join_edge"], p["default_edge"])
            buy_volume += b
            sell_volume += s

            result[Product.SQUID_INK] = orders

        # Update capital and return result
        capital += 1
        traderObject["capital"] = capital
        traderData = jsonpickle.encode(traderObject)

        return result, 0, traderData
