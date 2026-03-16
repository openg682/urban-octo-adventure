from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict, Tuple
import jsonpickle
import numpy as np


class Product:
    TOMATOES = "TOMATOES"
    EMERALDS = "EMERALDS"


# ── Parameters calibrated from 2 days of price data ───────────────────────────
#
# TOMATOES  mid avg ~4990, spread ~13  → edge of ~6-7 each side, moderate vol
# EMERALDS  mid avg 10000, spread ~16  → very stable; tight take, wide edge
# ──────────────────────────────────────────────────────────────────────────────
PARAMS = {
    Product.TOMATOES: {
        "fair_value": 5000,       # avg mid across both days ≈ 4990; rounded up
        "take_width": 6,          # take if best ask/bid is 6 inside fair value
        "clear_width": 8,         # reduce position if 8 outside fair value
        "disregard_edge": 15,     # ignore book levels within 15 of fair (noise)
        "join_edge": 5,           # join best level if it is ≤5 away from edge
        "default_edge": 7,        # default quote offset from fair value
        "soft_position_limit": 100,
    },
    Product.EMERALDS: {
        "fair_value": 10000,      # rock-solid across both days
        "take_width": 2,          # very tight – only grab genuine mispricings
        "clear_width": 1,
        "disregard_edge": 10,     # bids sit at 9992, asks at 10008 → ~8 each
        "join_edge": 1,
        "default_edge": 8,        # quote at 9992 / 10008 by default
        "soft_position_limit": 150,
    },
}


class Trader:
    def __init__(self):
        self.params = PARAMS
        self.LIMIT: Dict[str, int] = {p: 100 for p in PARAMS}

    # ── Generic order-taking ───────────────────────────────────────────────────
    def take_best_orders(
        self,
        product: str,
        fair_value: float,
        take_width: float,
        orders: List[Order],
        order_depth: OrderDepth,
        position: int,
    ) -> Tuple[int, int]:
        """Aggress the best ask/bid if it crosses fair_value ± take_width."""
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

    # ── Generic passive quoting ────────────────────────────────────────────────
    def market_make(
        self,
        product: str,
        orders: List[Order],
        bid: float,
        ask: float,
        position: int,
        buy_volume: int,
        sell_volume: int,
    ) -> Tuple[int, int]:
        """Post resting bid and ask for remaining capacity."""
        buy_qty = self.LIMIT[product] - (position + buy_volume)
        if buy_qty > 0:
            orders.append(Order(product, bid, buy_qty))

        sell_qty = self.LIMIT[product] + (position - sell_volume)
        if sell_qty > 0:
            orders.append(Order(product, ask, -sell_qty))

        return buy_volume, sell_volume

    def make_orders(
        self,
        product: str,
        order_depth: OrderDepth,
        fair_value: float,
        position: int,
        buy_volume: int,
        sell_volume: int,
        disregard_edge: float,
        join_edge: float,
        default_edge: float,
    ) -> Tuple[int, int]:
        """
        Determine bid/ask levels by inspecting the book, then call market_make.

        If there is a level outside disregard_edge that is within join_edge of
        our default quote, we join it; otherwise we undercut/overcut by 1 tick.
        """
        orders: List[Order] = []

        asks_outside = [p for p in order_depth.sell_orders if p > fair_value + disregard_edge]
        bids_outside  = [p for p in order_depth.buy_orders  if p < fair_value - disregard_edge]

        ask = round(fair_value + default_edge, 2)
        if asks_outside:
            best_ask = min(asks_outside)
            ask = best_ask if abs(best_ask - fair_value) <= join_edge else best_ask - 1

        bid = round(fair_value - default_edge, 2)
        if bids_outside:
            best_bid = max(bids_outside)
            bid = best_bid if abs(fair_value - best_bid) <= join_edge else best_bid + 1

        return self.market_make(product, orders, bid, ask, position, buy_volume, sell_volume)

    # ── Main entry point ───────────────────────────────────────────────────────
    def run(self, state: TradingState):
        result = {}
        traderObject = jsonpickle.decode(state.traderData) if state.traderData else {}

        for product in [Product.TOMATOES, Product.EMERALDS]:
            if product not in state.order_depths:
                continue

            orders: List[Order] = []
            order_depth = state.order_depths[product]
            position = state.position.get(product, 0)
            p = self.params[product]
            fair_value = p["fair_value"]

            buy_volume = sell_volume = 0

            # 1. Take mispriced orders aggressively
            b, s = self.take_best_orders(
                product, fair_value, p["take_width"],
                orders, order_depth, position,
            )
            buy_volume += b
            sell_volume += s

            # 2. Passively quote remaining capacity
            b, s = self.make_orders(
                product, order_depth, fair_value, position,
                buy_volume, sell_volume,
                p["disregard_edge"], p["join_edge"], p["default_edge"],
            )
            buy_volume += b
            sell_volume += s

            result[product] = orders

        # Persist any state across ticks
        traderData = jsonpickle.encode(traderObject)
        return result, 0, traderData
