# trading_bot.py

from datamodel import OrderDepth, TradingState, Order
from typing import List
import jsonpickle

class Product:
    RAINBOW_RESIN = "RAINBOW_RESIN"
    KELP = "KELP"
    SQUID_INK = "SQUID_INK"

PARAMS = {
    Product.RAINBOW_RESIN: {
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
        "take_width": 15,
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
}

class Trader:
    def __init__(self):
        self.params = PARAMS
        self.LIMIT = {p: 50 for p in PARAMS}

    def take_best_orders(self, product, fair_value, take_width, orders, order_depth, position):
        position_limit = self.LIMIT[product]
        buy_volume = sell_volume = 0

        # Take best ask if it's lower than fair value - width
        if order_depth.sell_orders:
            best_ask = min(order_depth.sell_orders)
            ask_volume = -order_depth.sell_orders[best_ask]
            if best_ask <= fair_value - take_width:
                qty = min(ask_volume, position_limit - position)
                if qty > 0:
                    orders.append(Order(product, best_ask, qty))
                    buy_volume += qty

        # Take best bid if it's higher than fair value + width
        if order_depth.buy_orders:
            best_bid = max(order_depth.buy_orders)
            bid_volume = order_depth.buy_orders[best_bid]
            if best_bid >= fair_value + take_width:
                qty = min(bid_volume, position_limit + position)
                if qty > 0:
                    orders.append(Order(product, best_bid, -qty))
                    sell_volume += qty

        return buy_volume, sell_volume

    def market_make(self, product, orders, bid, ask, position, buy_volume, sell_volume):
        buy_qty = self.LIMIT[product] - (position + buy_volume)
        if buy_qty > 0:
            orders.append(Order(product, bid, buy_qty))

        sell_qty = self.LIMIT[product] + (position - sell_volume)
        if sell_qty > 0:
            orders.append(Order(product, ask, -sell_qty))

        return buy_volume, sell_volume

    def clear_position(self, product, fair_value, width, orders, order_depth, position):
        buy_volume = sell_volume = 0
        fair_bid = round(fair_value - width)
        fair_ask = round(fair_value + width)

        if position > 0:
            # Sell to clear position
            clear_qty = sum(vol for price, vol in order_depth.buy_orders.items() if price >= fair_ask)
            clear_qty = min(clear_qty, position)
            if clear_qty > 0:
                orders.append(Order(product, fair_ask, -clear_qty))
                sell_volume += clear_qty

        elif position < 0:
            # Buy to clear position
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

        ask = round(fair_value + default_edge)
        if asks:
            best_ask = min(asks)
            ask = best_ask if abs(best_ask - fair_value) <= join_edge else best_ask - 1

        bid = round(fair_value - default_edge)
        if bids:
            best_bid = max(bids)
            bid = best_bid if abs(fair_value - best_bid) <= join_edge else best_bid + 1

        if manage_position:
            if position > soft_position_limit:
                ask -= 1
            elif position < -soft_position_limit:
                bid += 1

        return self.market_make(product, orders, bid, ask, position, buy_volume, sell_volume)

    def run(self, state: TradingState):
        result = {}
        traderObject = jsonpickle.decode(state.traderData) if state.traderData else {}
        capital = traderObject.get("capital", 0)

        # Stop trading once capital reaches 1000
        stop_trading = capital >= 1000

        for product in self.params:
            if product not in state.order_depths:
                continue

            orders = []
            position = state.position.get(product, 0)
            order_depth = state.order_depths[product]
            p = self.params[product]

            buy_volume = sell_volume = 0

            if not stop_trading:
                b, s = self.take_best_orders(product, p["fair_value"], p["take_width"], orders, order_depth, position)
                buy_volume += b
                sell_volume += s

                b, s = self.make_orders(
                    product, order_depth, p["fair_value"], position, buy_volume, sell_volume,
                    p["disregard_edge"], p["join_edge"], p["default_edge"], True, p["soft_position_limit"]
                )
                buy_volume += b
                sell_volume += s

            # Clear positions when capital reaches 1000
            if stop_trading:
                b, s = self.clear_position(product, p["fair_value"], p["clear_width"], orders, order_depth, position)
                buy_volume += b
                sell_volume += s

            result[product] = orders

        # Update capital (you can replace this with actual PnL calculation logic)
        capital += 10  # Simulated for testing; replace with actual PnL logic
        traderObject["capital"] = capital
        traderData = jsonpickle.encode(traderObject)
        conversions = 1

        return result, conversions, traderData
