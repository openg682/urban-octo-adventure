from datamodel import OrderDepth, TradingState, Order
from typing import List
import jsonpickle
import numpy as np

class Product:
    PICNIC_BASKET2 = "PICNIC_BASKET2"
    CROISSANTS = "CROISSANTS"
    JAMS = "JAMS"
    BASKET2_COMPONENTS = {CROISSANTS: 4, JAMS: 2}

PARAMS = {
    Product.PICNIC_BASKET2: {
        "fair_value": 30100.0,
        "take_width": 3,
        "clear_width": 2,
        "disregard_edge": 15,
        "join_edge": 1.5,
        "default_edge": 4,
        "soft_position_limit": 90,
    },
}

class Trader:
    def __init__(self):
        self.params = PARAMS
        self.LIMIT = {p: 100 for p in PARAMS}
        self.mid_price_history = {product: [] for product in PARAMS}
        self.window = 10
        self.default_min_spread = 1
        self.component_fair_values = {
            Product.CROISSANTS: 4300,  # Example fair values
            Product.JAMS: 6550,
        }

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
            orders.append(Order(product, int(round(bid)), buy_qty))

        sell_qty = self.LIMIT[product] + (position - sell_volume)
        if sell_qty > 0:
            orders.append(Order(product, int(round(ask)), -sell_qty))

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
        product = Product.PICNIC_BASKET2

        if product not in state.order_depths:
            return {}, 0, state.traderData

        orders = []
        order_depth = state.order_depths[product]
        position = state.position.get(product, 0)
        p = self.params[product]

        buy_volume = sell_volume = 0

        if order_depth.buy_orders and order_depth.sell_orders:
            mid_price = (max(order_depth.buy_orders) + min(order_depth.sell_orders)) / 2
            self.mid_price_history[product].append(mid_price)
            if len(self.mid_price_history[product]) > self.window:
                self.mid_price_history[product].pop(0)

        fair_value = p["fair_value"]
        # Update fair value based on components (example - you might need a more dynamic approach)
        fv_basket = sum(self.component_fair_values[comp] * qty for comp, qty in Product.BASKET2_COMPONENTS.items())
        fair_value = fv_basket

        b, s = self.take_best_orders(product, fair_value, p["take_width"], orders, order_depth, position)
        buy_volume += b
        sell_volume += s

        b, s = self.make_orders(
            product, order_depth, fair_value, position, buy_volume, sell_volume,
            p["disregard_edge"], p["join_edge"], p["default_edge"]
        )
        buy_volume += b
        sell_volume += s

        result[product] = orders
        capital += 1  # Simulating capital change
        traderObject["capital"] = capital
        traderData = jsonpickle.encode(traderObject)

        return result, 0, traderData
