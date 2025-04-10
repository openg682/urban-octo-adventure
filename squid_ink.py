from datamodel import OrderDepth, TradingState, Order
from typing import List
import jsonpickle
import numpy as np

class Product:
    SQUID_INK = "SQUID_INK"

PARAMS = {
    Product.SQUID_INK: {
        "fair_value": 1968,
        "take_width": 15,  # Decreased the take width for more aggressive trading
        "clear_width": 20,
        "disregard_edge": 80,  # Reduced the disregard edge to increase activity
        "join_edge": 15,  # Reduced join edge for faster market making
        "default_edge": 25,  # Adjusted the default edge for more aggressive pricing
        "soft_position_limit": 75,  # Increased the soft position limit for larger positions
    },
}

class Trader:
    def __init__(self):
        self.params = PARAMS
        self.LIMIT = {p: 75 for p in PARAMS}  # Increased position limits
        self.mid_price_history = {product: [] for product in PARAMS}
        self.window = 5  # Shorter window for faster reactions to price movements
        self.default_min_spread = 1

    def calculate_volatility(self, prices):
        """Calculate volatility using standard deviation."""
        if len(prices) > 1:
            return np.std(prices)
        return 0

    def calculate_dynamic_fair_value(self, prices):
        """Calculate fair value as a moving average."""
        if len(prices) > 1:
            return np.mean(prices)
        return self.params[Product.SQUID_INK]["fair_value"]
    
    def calculate_dynamic_take_width(self, volatility):
        """Adjust take width based on volatility, but more aggressively."""
        return max(10, volatility * 1.5)  # More aggressive adjustment for volatility

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
        """Market making logic for Squid Ink with increased aggression."""
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
        product = Product.SQUID_INK

        if product not in state.order_depths:
            return {}, 0, state.traderData

        orders = []
        order_depth = state.order_depths[product]
        position = state.position.get(product, 0)
        p = self.params[product]

        buy_volume = sell_volume = 0

        # Record mid price history for volatility calculation
        if order_depth.buy_orders and order_depth.sell_orders:
            mid_price = (max(order_depth.buy_orders) + min(order_depth.sell_orders)) / 2
            self.mid_price_history[product].append(mid_price)
            if len(self.mid_price_history[product]) > self.window:
                self.mid_price_history[product].pop(0)

        # Calculate dynamic fair value and volatility
        fair_value = self.calculate_dynamic_fair_value(self.mid_price_history[product])
        volatility = self.calculate_volatility(self.mid_price_history[product])
        take_width = self.calculate_dynamic_take_width(volatility)

        # Trading logic
        b, s = self.take_best_orders(product, fair_value, take_width, orders, order_depth, position)
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
