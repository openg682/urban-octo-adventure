from datamodel import OrderDepth, TradingState, Order
from typing import List
import jsonpickle
import numpy as np

class Product:
    JAMS = "JAMS"

PARAMS = {
    Product.JAMS: {
        "fair_value": 6550.0,
        "take_width": 1,
        "clear_width": 0.5,
        "disregard_edge": 6,
        "join_edge": 0.5,
        "default_edge": 1.5,
        "soft_position_limit": 315,
        "volatility_window": 10,  # Number of periods to calculate volatility
    },
}

class Trader:
    def __init__(self):
        self.params = PARAMS
        self.LIMIT = {p: 350 for p in PARAMS}
        self.mid_price_history = {product: [] for product in PARAMS}
        self.volatility_history = {product: [] for product in PARAMS}
        self.window = 10
        self.default_min_spread = 1

    def calculate_volatility(self, product, order_depth):
        # Calculate market volatility based on price range
        if len(self.mid_price_history[product]) < self.window:
            return 0.0  # Not enough data to calculate volatility
        
        # Use the price range (high - low) in the last few periods
        price_range = [max(order_depth.buy_orders) - min(order_depth.sell_orders) for _ in range(self.window)]
        volatility = np.std(price_range)  # Standard deviation of price range
        return volatility

    def dynamic_spread(self, product, fair_value, order_depth):
        # Adjust the spread based on volatility
        volatility = self.calculate_volatility(product, order_depth)
        if volatility == 0:
            return self.default_min_spread  # Default spread if there's no volatility
        
        # Dynamically adjust the spread, larger spread with higher volatility
        spread = max(self.default_min_spread, volatility * 0.5)
        return spread

    def dynamic_position_limit(self, product, order_depth):
        # Adjust position limit based on volatility
        volatility = self.calculate_volatility(product, order_depth)
        base_limit = self.LIMIT[product]
        
        # Larger position limit in less volatile markets
        if volatility < 50:
            return base_limit * 1.5
        else:
            return base_limit * 0.75

    def take_best_orders(self, product, fair_value, take_width, orders, order_depth, position):
        position_limit = self.dynamic_position_limit(product, order_depth)  # Adjust position limit based on volatility
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
        buy_qty = self.dynamic_position_limit(product, order_depth) - (position + buy_volume)
        if buy_qty > 0:
            orders.append(Order(product, round(bid, 1), buy_qty))

        sell_qty = self.dynamic_position_limit(product, order_depth) + (position - sell_volume)
        if sell_qty > 0:
            orders.append(Order(product, round(ask, 1), -sell_qty))

        return buy_volume, sell_volume

    def make_orders(self, product, order_depth, fair_value, position, buy_volume, sell_volume, disregard_edge, join_edge, default_edge):
        orders = []
        spread = self.dynamic_spread(product, fair_value, order_depth)  # Get dynamic spread
        asks = [p for p in order_depth.sell_orders if p > fair_value + disregard_edge]
        bids = [p for p in order_depth.buy_orders if p < fair_value - disregard_edge]
        tick_size = 0.1

        ask = round(fair_value + spread, 1)
        if asks:
            best_ask = min(asks)
            ask = min(ask, round(best_ask - tick_size, 1)) if abs(best_ask - fair_value) <= join_edge else min(ask, round(best_ask - tick_size, 1))

        bid = round(fair_value - spread, 1)
        if bids:
            best_bid = max(bids)
            bid = max(bid, round(best_bid + tick_size, 1)) if abs(fair_value - best_bid) <= join_edge else max(bid, round(best_bid + tick_size, 1))

        return self.market_make(product, orders, bid, ask, position, buy_volume, sell_volume, order_depth)

    def run(self, state: TradingState):
        result = {}
        traderObject = jsonpickle.decode(state.traderData) if state.traderData else {}
        capital = traderObject.get("capital", 0)
        initial_capital = traderObject.get("initial_capital", capital)
        product = Product.JAMS

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
