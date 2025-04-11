from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict, Optional
import jsonpickle
import numpy as np
import math

# Define Product constants matching data file names where applicable
class Product:
    KELP = "KELP"
    RAINFOREST_RESIN = "RAINFOREST_RESIN"
    SQUID_INK = "SQUID_INK"
    CROISSANTS = "CROISSANTS" # Match data file name
    JAMS = "JAMS"             # Match data file name
    DJEMBE = "DJEMBES"        # Match data file name (used DJEMBE in LIMIT/PARAMS keys for consistency)
    PICNIC_BASKET1 = "PICNIC_BASKET1"
    PICNIC_BASKET2 = "PICNIC_BASKET2"
    # Helper list of all product names matching the data files/class constants
    ALL = [KELP, RAINFOREST_RESIN, SQUID_INK, CROISSANTS, JAMS, DJEMBE, PICNIC_BASKET1, PICNIC_BASKET2]
    MARKET_MAKING_PRODUCTS = [KELP, RAINFOREST_RESIN, SQUID_INK, CROISSANTS, JAMS, DJEMBE] # Products for basic MM
    BASKET_PRODUCTS = [PICNIC_BASKET1, PICNIC_BASKET2]
    BASKET1_COMPONENTS = {CROISSANTS: 6, JAMS: 3, DJEMBE: 1}
    BASKET2_COMPONENTS = {CROISSANTS: 4, JAMS: 2}


# --- Parameters based on Data Analysis (Static values are fallback/initial only) ---
# Fair Value will be calculated dynamically; other params are starting points.
PARAMS = {
    # KELP: Relatively Stable
    Product.KELP: {
        "static_fair_value": 2032, # Fallback only
        "take_width": 1.5, "clear_width": 1, "disregard_edge": 10, "join_edge": 1, "default_edge": 2,
        "soft_position_limit": 90,
    },
    # RAINFOREST_RESIN: Stable around 10000
    Product.RAINFOREST_RESIN: {
        "static_fair_value": 10000, # Fallback only
        "take_width": 4, "clear_width": 3, "disregard_edge": 15, "join_edge": 2, "default_edge": 5,
        "soft_position_limit": 135,
    },
    # SQUID_INK: Drifts Down
    Product.SQUID_INK: {
        "static_fair_value": 1900, # Fallback only
        "take_width": 1.5, "clear_width": 1, "disregard_edge": 20, "join_edge": 1, "default_edge": 2,
        "soft_position_limit": 40,
    },
    # CROISSANTS: Drifts Down
    Product.CROISSANTS: {
        "static_fair_value": 4300, # Fallback only
        "take_width": 0.5, "clear_width": 0.5, "disregard_edge": 5, "join_edge": 0.5, "default_edge": 1,
        "soft_position_limit": 225,
    },
    # JAMS: Drifts Down
    Product.JAMS: {
        "static_fair_value": 6550, # Fallback only
        "take_width": 1, "clear_width": 0.5, "disregard_edge": 6, "join_edge": 0.5, "default_edge": 1.5,
        "soft_position_limit": 315,
    },
    # DJEMBE: Drifts Down
    Product.DJEMBE: { # Using DJEMBE as key, matches data name DJEMBES
        "static_fair_value": 13380, # Fallback only
        "take_width": 1, "clear_width": 0.5, "disregard_edge": 10, "join_edge": 0.5, "default_edge": 1,
        "soft_position_limit": 54,
    },
    # --- Baskets: Fair value derived from dynamic component values ---
    Product.PICNIC_BASKET1: {
        "static_fair_value": 58800, # Fallback only
        "take_width": 5, "clear_width": 3, "disregard_edge": 20, "join_edge": 2, "default_edge": 6,
        "soft_position_limit": 54,
    },
    Product.PICNIC_BASKET2: {
        "static_fair_value": 30100, # Fallback only
        "take_width": 3, "clear_width": 2, "disregard_edge": 15, "join_edge": 1.5, "default_edge": 4,
        "soft_position_limit": 90,
    },
}


class Trader:
    def __init__(self):
        # --- Persistent State Variables ---
        self.mid_price_history: Dict[str, List[float]] = {product: [] for product in Product.ALL}
        self.current_fair_values: Dict[str, float] = {} # Calculated each step
        self.pnl: Dict[str, float] = {product: 0.0 for product in Product.ALL} # Example state

        # --- Strategy Parameters ---
        self.params = PARAMS
        self.LIMIT = { # Hard position limits
            Product.KELP: 100, Product.RAINFOREST_RESIN: 150, Product.SQUID_INK: 45,
            Product.CROISSANTS: 250, Product.JAMS: 350, Product.DJEMBE: 60,
            Product.PICNIC_BASKET1: 60, Product.PICNIC_BASKET2: 100,
        }
        self.window = 10 # SMA window size
        self.arbitrage_thresholds = { # Per-basket arb thresholds
            Product.PICNIC_BASKET1: 5.0, Product.PICNIC_BASKET2: 4.0
        }
        # List of keys to automatically save/load from traderData
        self.persisted_keys = ["mid_price_history", "pnl"]

    def _load_trader_data(self, traderData: str):
        """Loads state variables from traderData string."""
        if traderData:
            try:
                data = jsonpickle.decode(traderData)
                for key in self.persisted_keys:
                    if key in data and data[key] is not None:
                         setattr(self, key, data[key])
            except Exception as e:
                print(f"Error loading traderData: {e}. Using defaults.")
        for product in Product.ALL:
            if not hasattr(self, 'mid_price_history') or product not in self.mid_price_history:
                 if not hasattr(self, 'mid_price_history'): self.mid_price_history = {}
                 self.mid_price_history[product] = []
            if not hasattr(self, 'pnl') or product not in self.pnl:
                 if not hasattr(self, 'pnl'): self.pnl = {}
                 self.pnl[product] = 0.0

    def _save_trader_data(self) -> str:
        """Saves state variables to traderData string."""
        data_to_save = {}
        for key in self.persisted_keys:
             if hasattr(self, key):
                data_to_save[key] = getattr(self, key)
        return jsonpickle.encode(data_to_save, unpicklable=False)


    def _get_mid_price(self, product: str, order_depth: OrderDepth) -> Optional[float]:
        """Safely calculates mid-price from order depth."""
        if order_depth.sell_orders and order_depth.buy_orders:
            try:
                best_ask = min(order_depth.sell_orders.keys())
                best_bid = max(order_depth.buy_orders.keys())
                if best_ask > best_bid: return (best_ask + best_bid) / 2.0
                else: return float(best_bid)
            except Exception: return None
        return None

    def _update_fair_value(self, product: str, state: TradingState):
        """Calculates and updates the dynamic fair value using SMA."""
        current_mid_price = None
        order_depth = state.order_depths.get(product)

        if order_depth: current_mid_price = self._get_mid_price(product, order_depth)

        if current_mid_price is not None:
            if product not in self.mid_price_history: self.mid_price_history[product] = []
            self.mid_price_history[product].append(current_mid_price)
            if len(self.mid_price_history[product]) > self.window:
                self.mid_price_history[product] = self.mid_price_history[product][-self.window:]

        history = self.mid_price_history.get(product, [])
        if history:
            min_points_for_sma = max(1, self.window // 2)
            if len(history) >= min_points_for_sma: fair_value = np.mean(history)
            else: fair_value = history[-1]
            self.current_fair_values[product] = fair_value
        else:
            if not hasattr(self, 'current_fair_values'): self.current_fair_values = {}
            self.current_fair_values[product] = self.params[product]["static_fair_value"]

        if product == Product.PICNIC_BASKET1:
            fv_basket = 0.0; components_ready = True
            for comp, qty in Product.BASKET1_COMPONENTS.items():
                 comp_fv = self.current_fair_values.get(comp)
                 if comp_fv is not None: fv_basket += qty * comp_fv
                 else: components_ready = False; break
            if components_ready: self.current_fair_values[product] = fv_basket

        elif product == Product.PICNIC_BASKET2:
            fv_basket = 0.0; components_ready = True
            for comp, qty in Product.BASKET2_COMPONENTS.items():
                 comp_fv = self.current_fair_values.get(comp)
                 if comp_fv is not None: fv_basket += qty * comp_fv
                 else: components_ready = False; break
            if components_ready: self.current_fair_values[product] = fv_basket

        return self.current_fair_values.get(product, self.params[product]["static_fair_value"])

    def _take_best_orders(self, product, fair_value, take_width, orders, order_depth, position):
        position_limit_hard = self.LIMIT[product]
        position_limit_soft = self.params[product]["soft_position_limit"]
        buy_volume = sell_volume = 0
        if abs(position) >= position_limit_hard: return 0, 0

        if order_depth.sell_orders:
             try:
                best_ask = min(order_depth.sell_orders)
                if best_ask <= fair_value - take_width:
                    ask_volume = -order_depth.sell_orders[best_ask]
                    if position < 0: max_qty_soft = position_limit_hard - position
                    else: max_qty_soft = max(0, position_limit_soft - position)
                    qty_allowed = min(ask_volume, max_qty_soft)
                    qty_allowed = min(qty_allowed, position_limit_hard - position)
                    qty = max(0, int(qty_allowed))
                    if qty > 0: orders.append(Order(product, best_ask, qty)); buy_volume += qty
             except Exception as e: print(f"Error taking ask {product}: {e}")

        if order_depth.buy_orders:
            try:
                best_bid = max(order_depth.buy_orders)
                if best_bid >= fair_value + take_width:
                    bid_volume = order_depth.buy_orders[best_bid]
                    if position > 0: max_qty_soft = position_limit_hard + position
                    else: max_qty_soft = max(0, position_limit_soft + position)
                    qty_allowed = min(bid_volume, max_qty_soft)
                    qty_allowed = min(qty_allowed, position_limit_hard + position)
                    qty = max(0, int(qty_allowed))
                    if qty > 0: orders.append(Order(product, best_bid, -qty)); sell_volume += qty
            except Exception as e: print(f"Error taking bid {product}: {e}")
        return buy_volume, sell_volume

    def _market_make(self, product, orders, bid, ask, position, buy_volume, sell_volume):
        position_limit_hard = self.LIMIT[product]
        position_limit_soft = self.params[product]["soft_position_limit"]
        current_buy_exposure = position + buy_volume
        buy_target = position_limit_soft
        buy_qty = max(0, buy_target - current_buy_exposure)
        buy_qty = min(buy_qty, max(0, position_limit_hard - current_buy_exposure))
        buy_qty = int(buy_qty)
        if buy_qty > 0: orders.append(Order(product, bid, buy_qty))
        current_sell_exposure = position - sell_volume
        sell_target = -position_limit_soft
        sell_qty = max(0, current_sell_exposure - sell_target)
        sell_qty = min(sell_qty, max(0, position_limit_hard + current_sell_exposure))
        sell_qty = int(sell_qty)
        if sell_qty > 0: orders.append(Order(product, ask, -sell_qty))
        return

    def _make_orders(self, product, order_depth, fair_value, position, buy_volume, sell_volume):
        orders = []; p = self.params[product]; pos = position
        soft_limit = p["soft_position_limit"]; join_edge = p["join_edge"]
        ask_edge = p["default_edge"]; bid_edge = p["default_edge"]
        skew_threshold = soft_limit * 0.5; clear_width_val = p["clear_width"]
        if abs(pos) > skew_threshold and soft_limit > 0:
             skew_factor = min(1.0, (abs(pos) - skew_threshold) / (soft_limit - skew_threshold + 1e-6))
             skew_amount = clear_width_val * skew_factor
             if pos > 0: ask_edge -= skew_amount; bid_edge += skew_amount
             else: bid_edge -= skew_amount; ask_edge += skew_amount
        min_edge = 0.01; ask_edge = max(min_edge, ask_edge); bid_edge = max(min_edge, bid_edge)
        is_resin = (product == Product.RAINFOREST_RESIN)
        round_digits = 4 if is_resin else 2
        tick_size = 0.0001 if is_resin else 0.01
        default_ask = round(fair_value + ask_edge, round_digits)
        default_bid = round(fair_value - bid_edge, round_digits)
        ask, bid = default_ask, default_bid
        try:
            if order_depth.sell_orders:
                best_ask_in_book = min(order_depth.sell_orders.keys())
                if best_ask_in_book <= fair_value + join_edge: ask = min(default_ask, round(best_ask_in_book - tick_size, round_digits))
            if order_depth.buy_orders:
                best_bid_in_book = max(order_depth.buy_orders.keys())
                if best_bid_in_book >= fair_value - join_edge: bid = max(default_bid, round(best_bid_in_book + tick_size, round_digits))
        except Exception as e: print(f"Error applying joining logic {product}: {e}")
        if bid >= ask - tick_size / 2:
             mid_point = round(fair_value, round_digits)
             spread = p["default_edge"] * 2
             bid = round(mid_point - spread / 2, round_digits)
             ask = round(mid_point + spread / 2, round_digits)
             if bid >= ask: ask = bid + tick_size
        self._market_make(product, orders, bid, ask, pos, buy_volume, sell_volume)
        return orders

    def arbitrage_baskets(self, state: TradingState):
        orders: List[Order] = []; order_depths = state.order_depths; positions = state.position
        basket1_prod = Product.PICNIC_BASKET1; required_comps1 = Product.BASKET1_COMPONENTS
        component_prods1 = list(required_comps1.keys()); threshold1 = self.arbitrage_thresholds[basket1_prod]
        if basket1_prod in order_depths and all(comp in order_depths for comp in component_prods1):
            basket1_depth = order_depths[basket1_prod]; component_depths1 = {comp: order_depths[comp] for comp in component_prods1}
            basket1_pos = positions.get(basket1_prod, 0); component_pos1 = {comp: positions.get(comp, 0) for comp in component_prods1}
            if basket1_depth.sell_orders and all(comp in component_depths1 and component_depths1[comp].buy_orders for comp in component_prods1):
                try:
                    best_basket1_ask = min(basket1_depth.sell_orders); best_comp_bids1 = {comp: max(component_depths1[comp].buy_orders) for comp in component_prods1}
                    comp_sale_value = sum(best_comp_bids1[comp] * qty for comp, qty in required_comps1.items()); potential_profit = comp_sale_value - best_basket1_ask
                    if potential_profit > threshold1:
                        basket_ask_vol = -basket1_depth.sell_orders[best_basket1_ask]; comp_bid_vols = {comp: component_depths1[comp].buy_orders[best_comp_bids1[comp]] for comp in component_prods1}
                        max_vol_from_comps = min(comp_bid_vols[comp] // qty for comp, qty in required_comps1.items() if qty > 0)
                        max_vol_basket_pos = self.LIMIT[basket1_prod] - basket1_pos; max_vol_comps_pos = min((self.LIMIT[comp] + component_pos1[comp]) // qty for comp, qty in required_comps1.items() if qty > 0)
                        trade_vol = min(basket_ask_vol, max_vol_from_comps, max_vol_basket_pos, max_vol_comps_pos); trade_vol = max(0, int(trade_vol))
                        if trade_vol > 0:
                            orders.append(Order(basket1_prod, best_basket1_ask, trade_vol))
                            for comp, qty in required_comps1.items(): orders.append(Order(comp, best_comp_bids1[comp], -trade_vol * qty))
                except Exception as e: print(f"Error in Buy Basket 1 Arb: {e}")
            if basket1_depth.buy_orders and all(comp in component_depths1 and component_depths1[comp].sell_orders for comp in component_prods1):
                try:
                    best_basket1_bid = max(basket1_depth.buy_orders); best_comp_asks1 = {comp: min(component_depths1[comp].sell_orders) for comp in component_prods1}
                    comp_buy_cost = sum(best_comp_asks1[comp] * qty for comp, qty in required_comps1.items()); potential_profit = best_basket1_bid - comp_buy_cost
                    if potential_profit > threshold1:
                        basket_bid_vol = basket1_depth.buy_orders[best_basket1_bid]; comp_ask_vols = {comp: -component_depths1[comp].sell_orders[best_comp_asks1[comp]] for comp in component_prods1}
                        max_vol_from_comps = min(comp_ask_vols[comp] // qty for comp, qty in required_comps1.items() if qty > 0)
                        max_vol_basket_pos = self.LIMIT[basket1_prod] + basket1_pos; max_vol_comps_pos = min((self.LIMIT[comp] - component_pos1[comp]) // qty for comp, qty in required_comps1.items() if qty > 0)
                        trade_vol = min(basket_bid_vol, max_vol_from_comps, max_vol_basket_pos, max_vol_comps_pos); trade_vol = max(0, int(trade_vol))
                        if trade_vol > 0:
                            orders.append(Order(basket1_prod, best_basket1_bid, -trade_vol))
                            for comp, qty in required_comps1.items(): orders.append(Order(comp, best_comp_asks1[comp], trade_vol * qty))
                except Exception as e: print(f"Error in Sell Basket 1 Arb: {e}")

        basket2_prod = Product.PICNIC_BASKET2; required_comps2 = Product.BASKET2_COMPONENTS
        component_prods2 = list(required_comps2.keys()); threshold2 = self.arbitrage_thresholds[basket2_prod]
        if basket2_prod in order_depths and all(comp in order_depths for comp in component_prods2):
            basket2_depth = order_depths[basket2_prod]; component_depths2 = {comp: order_depths[comp] for comp in component_prods2}
            basket2_pos = positions.get(basket2_prod, 0); component_pos2 = {comp: positions.get(comp, 0) for comp in component_prods2}
            if basket2_depth.sell_orders and all(comp in component_depths2 and component_depths2[comp].buy_orders for comp in component_prods2):
                 try:
                    best_basket2_ask = min(basket2_depth.sell_orders); best_comp_bids2 = {comp: max(component_depths2[comp].buy_orders) for comp in component_prods2}
                    comp_sale_value = sum(best_comp_bids2[comp] * qty for comp, qty in required_comps2.items()); potential_profit = comp_sale_value - best_basket2_ask
                    if potential_profit > threshold2:
                        basket_ask_vol = -basket2_depth.sell_orders[best_basket2_ask]; comp_bid_vols = {comp: component_depths2[comp].buy_orders[best_comp_bids2[comp]] for comp in component_prods2}
                        max_vol_from_comps = min(comp_bid_vols[comp] // qty for comp, qty in required_comps2.items() if qty > 0)
                        max_vol_basket_pos = self.LIMIT[basket2_prod] - basket2_pos; max_vol_comps_pos = min((self.LIMIT[comp] + component_pos2[comp]) // qty for comp, qty in required_comps2.items() if qty > 0)
                        trade_vol = min(basket_ask_vol, max_vol_from_comps, max_vol_basket_pos, max_vol_comps_pos); trade_vol = max(0, int(trade_vol))
                        if trade_vol > 0:
                            orders.append(Order(basket2_prod, best_basket2_ask, trade_vol))
                            for comp, qty in required_comps2.items(): orders.append(Order(comp, best_comp_bids2[comp], -trade_vol * qty))
                 except Exception as e: print(f"Error in Buy Basket 2 Arb: {e}")
            if basket2_depth.buy_orders and all(comp in component_depths2 and component_depths2[comp].sell_orders for comp in component_prods2):
                try:
                    best_basket2_bid = max(basket2_depth.buy_orders); best_comp_asks2 = {comp: min(component_depths2[comp].sell_orders) for comp in component_prods2}
                    comp_buy_cost = sum(best_comp_asks2[comp] * qty for comp, qty in required_comps2.items()); potential_profit = best_basket2_bid - comp_buy_cost
                    if potential_profit > threshold2:
                        basket_bid_vol = basket2_depth.buy_orders[best_basket2_bid]; comp_ask_vols = {comp: -component_depths2[comp].sell_orders[best_comp_asks2[comp]] for comp in component_prods2}
                        max_vol_from_comps = min(comp_ask_vols[comp] // qty for comp, qty in required_comps2.items() if qty > 0)
                        max_vol_basket_pos = self.LIMIT[basket2_prod] + basket2_pos; max_vol_comps_pos = min((self.LIMIT[comp] - component_pos2[comp]) // qty for comp, qty in required_comps2.items() if qty > 0)
                        trade_vol = min(basket_bid_vol, max_vol_from_comps, max_vol_basket_pos, max_vol_comps_pos); trade_vol = max(0, int(trade_vol))
                        if trade_vol > 0:
                            orders.append(Order(basket2_prod, best_basket2_bid, -trade_vol))
                            for comp, qty in required_comps2.items(): orders.append(Order(comp, best_comp_asks2[comp], trade_vol * qty))
                except Exception as e: print(f"Error in Sell Basket 2 Arb: {e}")
        return orders


    # Main Run Function
    def run(self, state: TradingState):
        self._load_trader_data(state.traderData)
        result: Dict[str, List[Order]] = {product: [] for product in Product.ALL}
        self.current_fair_values = {}

        # Calculate Fair Values
        component_products = set(Product.BASKET1_COMPONENTS.keys()) | set(Product.BASKET2_COMPONENTS.keys())
        other_mm_products = [p for p in Product.MARKET_MAKING_PRODUCTS if p not in component_products]
        for product in list(component_products) + other_mm_products:
             if product in state.order_depths: self._update_fair_value(product, state)
        for product in Product.BASKET_PRODUCTS:
             if product in state.order_depths: self._update_fair_value(product, state)

        # Market Making Loop
        products_to_mm = Product.MARKET_MAKING_PRODUCTS
        for product in products_to_mm:
            if product in state.order_depths and product in self.current_fair_values:
                order_depth = state.order_depths[product]
                position = state.position.get(product, 0)
                p_params = self.params[product]
                fair_value = self.current_fair_values[product]
                mm_orders_take = []
                buy_vol_take, sell_vol_take = self._take_best_orders(product, fair_value, p_params["take_width"], mm_orders_take, order_depth, position)
                result[product].extend(mm_orders_take)
                mm_orders_make = self._make_orders(product, order_depth, fair_value, position, buy_vol_take, sell_vol_take)
                result[product].extend(mm_orders_make)

        # Basket Arbitrage
        arbitrage_orders = self.arbitrage_baskets(state)
        for order in arbitrage_orders:
            if order.symbol in result: result[order.symbol].append(order)
            else: print(f"Warning: Arbitrage order generated for unexpected product symbol '{order.symbol}'. Discarding.")

        # --- Save Persistent State ---
        traderData = self._save_trader_data()

        # --- Prepare the final return dictionary ---
        conversions = 0
        final_result = {        # *** Correct dictionary assignment ***
            "Orders": result,
            "Conversion": conversions,
            "TraderData": traderData
        }

        # --- Return the single dictionary ---
        return final_result     # *** Return the constructed dictionary ***
