from datamodel import OrderDepth, TradingState, Order
import jsonpickle
import numpy as np

class Product:
    SQUID_INK = "SQUID_INK"

PARAMS = {
    Product.SQUID_INK: {
        "fair_value": 1968,
        "take_width": 5,
        "clear_width": 20,
        "disregard_edge": 10,
        "join_edge": 1,
        "default_edge": 15,
        "soft_position_limit": 45,
    }
}

class Trader:
    def __init__(self):
        self.params = PARAMS
        self.LIMIT = {Product.SQUID_INK: 50}
        self.max_drawdown = -500
        self.capital_stop_limit = 30000
        self.max_profit_limit = 2500
        self.mid_price_history = {Product.SQUID_INK: []}
        self.window = 10
        self.default_min_spread = 1

    def run(self, state: TradingState):
        product = Product.SQUID_INK
        result = {}
        traderObject = jsonpickle.decode(state.traderData) if state.traderData else {}
        capital = traderObject.get("capital", 0)
        initial_capital = traderObject.get("initial_capital", capital)
        profit = capital - initial_capital
        stop_trading = capital >= self.capital_stop_limit or capital <= self.max_drawdown or profit >= self.max_profit_limit

        orders = []
        if product in state.order_depths:
            order_depth = state.order_depths[product]
            position = state.position.get(product, 0)
            p = self.params[product]

            if order_depth.buy_orders and order_depth.sell_orders:
                mid_price = (max(order_depth.buy_orders) + min(order_depth.sell_orders)) / 2
                self.mid_price_history[product].append(mid_price)
                if len(self.mid_price_history[product]) > self.window:
                    self.mid_price_history[product].pop(0)

                volatility = np.std(self.mid_price_history[product]) if len(self.mid_price_history[product]) >= 2 else 0
                take_width = max(10, volatility * 3)
                fair_value = np.mean(self.mid_price_history[product])
            else:
                take_width = p["take_width"]
                fair_value = p["fair_value"]

            if not stop_trading:
                # Take liquidity
                if order_depth.sell_orders:
                    best_ask = min(order_depth.sell_orders)
                    ask_volume = -order_depth.sell_orders[best_ask]
                    if best_ask <= fair_value - take_width:
                        qty = min(ask_volume, self.LIMIT[product] - position)
                        if qty > 0:
                            orders.append(Order(product, best_ask, qty))

                if order_depth.buy_orders:
                    best_bid = max(order_depth.buy_orders)
                    bid_volume = order_depth.buy_orders[best_bid]
                    if best_bid >= fair_value + take_width:
                        qty = min(bid_volume, self.LIMIT[product] + position)
                        if qty > 0:
                            orders.append(Order(product, best_bid, -qty))

                # Market making with skew
                bid = round(fair_value - p["default_edge"], 2)
                ask = round(fair_value + p["default_edge"], 2)

                if position > p["soft_position_limit"]:
                    ask -= 1
                elif position < -p["soft_position_limit"]:
                    bid += 1

                buy_qty = self.LIMIT[product] - position
                if buy_qty > 0:
                    orders.append(Order(product, bid, buy_qty))

                sell_qty = self.LIMIT[product] + position
                if sell_qty > 0:
                    orders.append(Order(product, ask, -sell_qty))

            else:
                # Clear positions
                fair_bid = round(fair_value - p["clear_width"], 2)
                fair_ask = round(fair_value + p["clear_width"], 2)

                if position > 0:
                    clear_qty = sum(vol for price, vol in order_depth.buy_orders.items() if price >= fair_ask)
                    clear_qty = min(clear_qty, position)
                    if clear_qty > 0:
                        orders.append(Order(product, fair_ask, -clear_qty))
                elif position < 0:
                    clear_qty = sum(-vol for price, vol in order_depth.sell_orders.items() if price <= fair_bid)
                    clear_qty = min(clear_qty, -position)
                    if clear_qty > 0:
                        orders.append(Order(product, fair_bid, clear_qty))

            result[product] = orders

        capital += 10
        traderObject["capital"] = capital
        traderData = jsonpickle.encode(traderObject)
        return result, 1, traderData
