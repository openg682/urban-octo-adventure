from datamodel import OrderDepth, TradingState, Order
from typing import List
import jsonpickle
import numpy as np

class Product:
    PICNIC_BASKET1 = "PICNIC_BASKET1"
    PICNIC_BASKET2 = "PICNIC_BASKET2"
    CROISSANTS = "CROISSANTS"
    JAMS = "JAMS"
    DJEMBE = "DJEMBE"
    BASKET1_COMPONENTS = {CROISSANTS: 6, JAMS: 3, DJEMBE: 1}
    BASKET2_COMPONENTS = {CROISSANTS: 4, JAMS: 2}

PARAMS = {
    Product.PICNIC_BASKET1: {"fair_value": 58800.0, "take_width": 5, "clear_width": 3, "disregard_edge": 20, "join_edge": 2, "default_edge": 6, "soft_position_limit": 54},
    Product.PICNIC_BASKET2: {"fair_value": 30100.0, "take_width": 3, "clear_width": 2, "disregard_edge": 15, "join_edge": 1.5, "default_edge": 4, "soft_position_limit": 90},
    Product.CROISSANTS: {"fair_value": 4300.0, "take_width": 0.5, "clear_width": 0.5, "disregard_edge": 5, "join_edge": 0.5, "default_edge": 1, "soft_position_limit": 225},
    Product.JAMS: {"fair_value": 6550.0, "take_width": 1, "clear_width": 0.5, "disregard_edge": 6, "join_edge": 0.5, "default_edge": 1.5, "soft_position_limit": 315},
    Product.DJEMBE: {"fair_value": 13380.0, "take_width": 1, "clear_width": 0.5, "disregard_edge": 10, "join_edge": 0.5, "default_edge": 1, "soft_position_limit": 54},
}

class Trader:
    def __init__(self):
        self.params = PARAMS
        self.LIMIT = {
            Product.PICNIC_BASKET1: 60,
            Product.PICNIC_BASKET2: 100,
            Product.CROISSANTS: 250,
            Product.JAMS: 350,
            Product.DJEMBE: 60,
        }
        self.mid_price_history = {product: [] for product in PARAMS}
        self.window = 10
        self.default_min_spread = 1
        self.arbitrage_thresholds = {
            Product.PICNIC_BASKET1: 5.0,
            Product.PICNIC_BASKET2: 4.0
        }

    def take_best_orders(self, product, fair_value, take_width, orders, order_depth, position):
        # Arbitrage doesn't directly use this in the same way as single product strategies
        return 0, 0

    def market_make(self, product, orders, bid, ask, position, buy_volume, sell_volume, order_depth):
        # Arbitrage doesn't directly use this in the same way as single product strategies
        return 0, 0

    def make_orders(self, product, order_depth, fair_value, position, buy_volume, sell_volume, disregard_edge, join_edge, default_edge):
        # Arbitrage doesn't directly use this in the same way as single product strategies
        return 0, 0

    def arbitrage_baskets(self, state: TradingState):
        orders: List[Order] = []
        order_depths = state.order_depths
        positions = state.position

        # --- Picnic Basket 1 ---
        basket1_prod = Product.PICNIC_BASKET1
        required_comps1 = Product.BASKET1_COMPONENTS
        component_prods1 = list(required_comps1.keys())
        threshold1 = self.arbitrage_thresholds[basket1_prod]
        if basket1_prod in order_depths and all(comp in order_depths for comp in component_prods1):
            basket1_depth = order_depths[basket1_prod]
            component_depths1 = {comp: order_depths[comp] for comp in component_prods1}
            basket1_pos = positions.get(basket1_prod, 0)
            component_pos1 = {comp: positions.get(comp, 0) for comp in component_prods1}

            if basket1_depth.sell_orders and all(comp in component_depths1 and component_depths1[comp].buy_orders for comp in component_prods1):
                try:
                    best_basket1_ask = min(basket1_depth.sell_orders)
                    best_comp_bids1 = {comp: max(component_depths1[comp].buy_orders) for comp in component_prods1}
                    comp_sale_value = sum(best_comp_bids1[comp] * qty for comp, qty in required_comps1.items())
                    potential_profit = comp_sale_value - best_basket1_ask
                    if potential_profit > threshold1:
                        basket_ask_vol = -basket1_depth.sell_orders[best_basket1_ask]
                        comp_bid_vols = {comp: component_depths1[comp].buy_orders[best_comp_bids1[comp]] for comp in component_prods1}
                        max_vol_from_comps = min(comp_bid_vols[comp] // qty for comp, qty in required_comps1.items() if qty > 0)
                        max_vol_basket_pos = self.LIMIT[basket1_prod] - basket1_pos
                        max_vol_comps_pos = min((self.LIMIT[comp] + component_pos1[comp]) // qty for comp, qty in required_comps1.items() if qty > 0)
                        trade_vol = min(basket_ask_vol, max_vol_from_comps, max_vol_basket_pos, max_vol_comps_pos)
                        trade_vol = max(0, int(trade_vol))
                        if trade_vol > 0:
                            orders.append(Order(basket1_prod, best_basket1_ask, trade_vol))
                            for comp, qty in required_comps1.items(): orders.append(Order(comp, best_comp_bids1[comp], -trade_vol * qty))
                except Exception as e: print(f"Error in Buy Basket 1 Arb: {e}")

            if basket1_depth.buy_orders and all(comp in component_depths1 and component_depths1[comp].sell_orders for comp in component_prods1):
                try:
                    best_basket1_bid = max(basket1_depth.buy_orders)
                    best_comp_asks1 = {comp: min(component_depths1[comp].sell_orders) for comp in component_prods1}
                    comp_buy_cost = sum(best_comp_asks1[comp] * qty for comp, qty in required_comps1.items())
                    potential_profit = best_basket1_bid - comp_buy_cost
                    if potential_profit > threshold1:
                        basket_bid_vol = basket1_depth.buy_orders[best_basket1_bid]
                        comp_ask_vols = {comp: -component_depths1[comp].sell_orders[best_comp_asks1[comp]] for comp in component_prods1}
                        max_vol_from_comps = min(comp_ask_vols[comp] // qty for comp, qty in required_comps1.items() if qty > 0)
                        max_vol_basket_pos = self.LIMIT[basket1_prod] + basket1_pos
                        max_vol_comps_pos = min((self.LIMIT[comp] - component_pos1[comp]) // qty for comp, qty in required_comps1.items() if qty > 0)
                        trade_vol = min(basket_bid_vol, max_vol_from_comps, max_vol_basket_pos, max_vol_comps_pos)
                        trade_vol = max(0, int(trade_vol))
                        if trade_vol > 0:
                            orders.append(Order(basket1_prod, best_basket1_bid, -trade_vol))
                            for comp, qty in required_comps1.items(): orders.append(Order(comp, best_comp_asks1[comp], trade_vol * qty))
                except Exception as e: print(f"Error in Sell Basket 1 Arb: {e}")
        return orders

    def run(self, state: TradingState):
        result = {}
        traderObject = jsonpickle.decode(state.traderData) if state.traderData else {}
        capital = traderObject.get("capital", 0)
        initial_capital = traderObject.get("initial_capital", capital)

        arbitrage_orders = self.arbitrage_baskets(state)
        for order in arbitrage_orders:
            if order.symbol in result:
                result[order.symbol].append(order)
            else:
                result[order.symbol] = [order]

        capital += 1  # Simulating capital change
        traderObject["capital"] = capital
        traderData = jsonpickle.encode(traderObject)

        return result, 0, traderData

