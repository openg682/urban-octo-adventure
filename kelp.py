from datamodel import OrderDepth, TradingState, Order
from typing import List
import jsonpickle
import numpy as np

class Product:
    KELP = "KELP"

PARAMS = {
    Product.KELP: {
        "fair_value": 2020,  # Keeping fair value fixed at 2020
        "take_width": 10,  # Default take width
        "clear_width": 10,  # Clearing width
        "disregard_edge": 10,  # Disregard edge
        "join_edge": 5,  # Join edge
        "default_edge": 10,  # Default edge
        "soft_position_limit": 100,  # Default position limit
    },
}

class Trader:
    def __init__(self):
        self.params = PARAMS
        self.LIMIT = {p: 100 for p in PARAMS}  # Soft position limit
        self.mid_price_history = {product: [] for product in PARAMS}
        self.window = 10  # History window for calculating volatility
        self.default_min_spread = 1

    def calculate_volatility(self, product):
        """Calculate volatility based on price history"""
        if len(self.mid_price_history[product]) < 2:
            return 0  # No volatility with less than 2 points of data
        return np.std(self.mid_price_history[product])  # Standard deviation of mid prices

    def adjust_parameters(self, product, volatility):
        """Dynamically adjust parameters based on volatility"""
        p = self.params[product]

        # Adjust take_width dynamically based on volatility
        take_width = p["take_width"] + volatility * 1.5  # Increase take width with higher volatility

        # Adjust disregard_edge dynamically
        disregard_edge = p["disregard_edge"] + volatility * 2  # Increase disregard edge with higher volatility

        # Adjust position limits dynamically based on volatility
        position_limit = min(self.LIMIT[product] * (1 + volatility * 0.5), 200)  # Max limit capped at 200

        # Adjust join_edge dynamically
        join_edge = p["join_edge"] + volatility * 0.5  # Small adjustment based on volatility

        # Adjust default_edge dynamically
        default_edge = p["default_edge"] + volatility * 0.5  # Adjust default edge for volatility

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
        product = Product.KELP

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

        volatility = self.calculate_volatility(product)
        take_width, disregard_edge, position_limit, join_edge, default_edge = self.adjust_parameters(product, volatility)

        fair_value = p["fair_value"]

        # Take the best orders with new dynamic strategy
        b, s = self.take_best_orders(product, fair_value, take_width, orders, order_depth, position)
        buy_volume += b
        sell_volume += s

        # Aggressively make orders based on dynamically adjusted values
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
