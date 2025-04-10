from datamodel import OrderDepth, TradingState, Order
import jsonpickle

class Product:
    RAINFOREST_RESIN = "RAINFOREST_RESIN"

PARAMS = {
    Product.RAINFOREST_RESIN: {
        "fair_value": 10000,
        "take_width": 0.001,
        "clear_width": 0.5,
        "disregard_edge": 0.01,
        "join_edge": 0.001,
        "default_edge": 0.001,
        "soft_position_limit": 50,
    }
}

class Trader:
    def __init__(self):
        self.params = PARAMS
        self.LIMIT = {Product.RAINFOREST_RESIN: 50}
        self.max_drawdown = -500
        self.capital_stop_limit = 30000
        self.max_profit_limit = 2500

    def run(self, state: TradingState):
        product = Product.RAINFOREST_RESIN
        result = {}
        traderObject = jsonpickle.decode(state.traderData) if state.traderData else {}
        capital = traderObject.get("capital", 0)
        initial_capital = traderObject.get("initial_capital", capital)
        profit = capital - initial_capital

        stop_trading = capital >= self.capital_stop_limit or capital <= self.max_drawdown or profit >= self.max_profit_limit

        orders = []
        if product in state.order_depths:
            position = state.position.get(product, 0)
            order_depth = state.order_depths[product]
            p = self.params[product]
            fair_value = p["fair_value"]
            limit = self.LIMIT[product]

            if not stop_trading:
                # Take orders
                if order_depth.sell_orders:
                    best_ask = min(order_depth.sell_orders)
                    ask_volume = -order_depth.sell_orders[best_ask]
                    if best_ask <= fair_value - p["take_width"]:
                        qty = min(ask_volume, limit - position)
                        if qty > 0:
                            orders.append(Order(product, best_ask, qty))

                if order_depth.buy_orders:
                    best_bid = max(order_depth.buy_orders)
                    bid_volume = order_depth.buy_orders[best_bid]
                    if best_bid >= fair_value + p["take_width"]:
                        qty = min(bid_volume, limit + position)
                        if qty > 0:
                            orders.append(Order(product, best_bid, -qty))

                # Market make always
                bid = round(fair_value - p["default_edge"], 2)
                ask = round(fair_value + p["default_edge"], 2)

                buy_qty = limit - position
                if buy_qty > 0:
                    orders.append(Order(product, bid, buy_qty))

                sell_qty = limit + position
                if sell_qty > 0:
                    orders.append(Order(product, ask, -sell_qty))

            else:
                # Clear position
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
