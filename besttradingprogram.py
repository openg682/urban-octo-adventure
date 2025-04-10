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
        self.mid_price_history = {product: [] for product in PARAMS}
        self.window = 10
        self.default_min_spread = 1.1
        self.max_drawdown = -500
        self.capital_stop_limit = 30000
        self.max_profit_limit = 2500

    def calculate_volatility(self, product):
        """Calculate volatility based on price history"""
        if len(self.mid_price_history[product]) < 2:
            return 0
        return np.std(self.mid_price_history[product])

    def adjust_parameters(self, product, volatility):
        """Dynamically adjust parameters based on volatility"""
        p = self.params[product]

        take_width = p["take_width"] + volatility * 1.5
        disregard_edge = p["disregard_edge"] + volatility * 2
        position_limit = min(self.LIMIT[product] * (1 + volatility * 0.5), 200)
        join_edge = p["join_edge"] + volatility * 0.5
        default_edge = p["default_edge"] + volatility * 0.5

        return take_width, disregard_edge, position_limit, join_edge, default_edge

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
        buy_qty = self.LIMIT[product] - (position + buy_volume)
        if buy_qty > 0:
            orders.append(Order(product, bid, buy_qty))

        sell_qty = self.LIMIT[product] + (position - sell_volume)
        if sell_qty > 0:
            orders.append(Order(product, ask, -sell_qty))

        return buy_volume, sell_volume

    def make_orders(self, product, order_depth, fair_value, position, buy_volume, sell_volume, disregard_edge, join_edge, default_edge):
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

        return self.market_make(product, orders, bid, ask, position, buy_volume, sell_volume, order_depth)

    def run(self, state: TradingState):
        result = {}
        traderObject = jsonpickle.decode(state.traderData) if state.traderData else {}
        capital = traderObject.get("capital", 0)
        initial_capital = traderObject.get("initial_capital", capital)

        orders = []
        for product in PARAMS.keys():
            if product not in state.order_depths:
                continue

            order_depth = state.order_depths[product]
            position = state.position.get(product, 0)
            p = self.params[product]

            buy_volume = sell_volume = 0

            if order_depth.buy_orders and order_depth.sell_orders:
                mid_price = (max(order_depth.buy_orders) + min(order_depth.sell_orders)) / 2
                self.mid_price_history[product].append(mid_price)
                if len(self.mid_price_history[product]) > self.window:
                    self.mid_price_history[product].pop(0)

            volatility = self.calculate_volatility(product)
            take_width, disregard_edge, position_limit, join_edge, default_edge = self.adjust_parameters(product, volatility)
            fair_value = p["fair_value"]

            b, s = self.take_best_orders(product, fair_value, take_width, orders, order_depth, position)
            buy_volume += b
            sell_volume += s

            b, s = self.make_orders(
                product, order_depth, fair_value, position, buy_volume, sell_volume,
                disregard_edge, join_edge, default_edge
            )
            buy_volume += b
            sell_volume += s

            result[product] = orders

        capital += 1
        traderObject["capital"] = capital
        traderData = jsonpickle.encode(traderObject)

        return result, 0, traderData
