# trading_bot.py (Version with SQUID_INK Mean Reversion Strategy)

from datamodel import OrderDepth, TradingState, Order, Trade
from typing import List, Dict
import jsonpickle
import numpy as np
import collections

class Product:
    RAINFOREST_RESIN = "RAINFOREST_RESIN"
    KELP = "KELP"
    SQUID_INK = "SQUID_INK"

# Updated PARAMS to include thresholds for SQUID_INK strategy
PARAMS = {
    Product.RAINFOREST_RESIN: {
        "fair_value": 10000, # Will be updated dynamically
        "take_width": 2,
        "clear_width": 0.5,
        "disregard_edge": 3,
        "join_edge": 1,
        "default_edge": 2,
        "soft_position_limit": 25,
        "volatility_window": 10,
    },
    Product.KELP: {
        "fair_value": 2030, # Will be updated dynamically
        "take_width": 15, # Updated dynamically based on volatility
        "clear_width": 5,
        "disregard_edge": 25,
        "join_edge": 10,
        "default_edge": 20,
        "soft_position_limit": 30,
        "volatility_window": 10,
    },
    Product.SQUID_INK: {
        "fair_value": 1968, # Will be updated dynamically (mean)
        "volatility_window": 10, # Window for mean/std dev calculation
        "deviation_entry_threshold": 1.75, # Z-score threshold to enter a position (tune this)
        "deviation_exit_threshold": 0.45,  # Z-score threshold to exit a position (tune this)
        "soft_position_limit": 30, # Still useful for scaling orders potentially
        "clear_width": 20, # Used for emergency clearing
    },
}

class Trader:
    def __init__(self):
        """
        Initializes the Trader class.
        """
        self.params = PARAMS
        self.LIMIT = {p: 50 for p in PARAMS} # Position limit per product
        self.max_drawdown = -500
        self.capital_stop_limit = 500
        self.max_profit_limit = 1400
        self.mid_price_history = {product: collections.deque(maxlen=p["volatility_window"]) for product, p in PARAMS.items()}
        self.min_spread = 1 # Used for non-SQUID_INK products
        self.initial_capital = None

    # Methods take_best_orders, market_make, make_orders are kept for other products
    # but will NOT be used for SQUID_INK in the modified run method.

    def take_best_orders(self, product, fair_value, take_width, orders, order_depth, position):
        """ (Kept for non-SQUID_INK products) """
        position_limit = self.LIMIT[product]
        buy_volume = sell_volume = 0
        if abs(position) >= position_limit: return 0, 0
        if order_depth.sell_orders:
            best_ask = min(order_depth.sell_orders)
            ask_volume = -order_depth.sell_orders[best_ask]
            if best_ask <= fair_value - take_width:
                qty = min(ask_volume, position_limit - position)
                if qty > 0:
                    print(f"TAKE BUY: {product} {qty}@{best_ask}")
                    orders.append(Order(product, best_ask, qty))
                    buy_volume += qty
        if order_depth.buy_orders:
            best_bid = max(order_depth.buy_orders)
            bid_volume = order_depth.buy_orders[best_bid]
            if best_bid >= fair_value + take_width:
                qty = min(bid_volume, position_limit + position)
                if qty > 0:
                    print(f"TAKE SELL: {product} {qty}@{best_bid}")
                    orders.append(Order(product, best_bid, -qty))
                    sell_volume += qty
        return buy_volume, sell_volume

    def market_make(self, product, orders, bid, ask, position, buy_volume, sell_volume, order_depth):
        """ (Kept for non-SQUID_INK products) """
        if order_depth.buy_orders and order_depth.sell_orders:
            best_bid_market = max(order_depth.buy_orders)
            best_ask_market = min(order_depth.sell_orders)
            if best_ask_market - best_bid_market < self.min_spread:
                 print(f"SPREAD TOO TIGHT: {product} ({best_ask_market - best_bid_market}), skipping market make.")
                 return buy_volume, sell_volume
        buy_qty = self.LIMIT[product] - (position + buy_volume)
        if buy_qty > 0: orders.append(Order(product, bid, buy_qty))
        sell_qty = self.LIMIT[product] + (position - sell_volume)
        if sell_qty > 0: orders.append(Order(product, ask, -sell_qty))
        return buy_volume, sell_volume

    def clear_position(self, product, fair_value, width, orders, order_depth, position):
        """ (Used for all products during stop_trading or potentially SQUID_INK exit) """
        buy_volume = sell_volume = 0
        # Use mid_price if available for clearing, otherwise fair_value
        clear_price = fair_value
        if order_depth.buy_orders and order_depth.sell_orders:
             clear_price = (max(order_depth.buy_orders) + min(order_depth.sell_orders)) / 2

        # Define prices for clearing orders - maybe use market prices for faster exit?
        clear_bid = min(order_depth.sell_orders) if order_depth.sell_orders else round(clear_price - width)
        clear_ask = max(order_depth.buy_orders) if order_depth.buy_orders else round(clear_price + width)

        if position > 0: # Need to sell
            qty_to_clear = position
            print(f"CLEAR SELL: {product} {qty_to_clear}@{clear_ask}")
            orders.append(Order(product, clear_ask, -qty_to_clear)) # Sell order at best bid
            sell_volume += qty_to_clear
        elif position < 0: # Need to buy
            qty_to_clear = -position
            print(f"CLEAR BUY: {product} {qty_to_clear}@{clear_bid}")
            orders.append(Order(product, clear_bid, qty_to_clear)) # Buy order at best ask
            buy_volume += qty_to_clear
        return buy_volume, sell_volume

    def make_orders(self, product, order_depth, fair_value, position, buy_volume, sell_volume, disregard_edge, join_edge, default_edge, manage_position, soft_position_limit):
        """ (Kept for non-SQUID_INK products) """
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
            if position > soft_position_limit: ask -= 1
            elif position < -soft_position_limit: bid += 1
        return self.market_make(product, orders, bid, ask, position, buy_volume, sell_volume, order_depth)

    # *** MODIFIED run Function ***
    def run(self, state: TradingState) -> Dict[str, List[Order]]:
        """
        Main execution function. Includes SQUID_INK mean reversion strategy.
        """
        result = {}
        traderObject = jsonpickle.decode(state.traderData) if state.traderData else {}
        self.initial_capital = traderObject.get("initial_capital", self.initial_capital)
        current_capital = traderObject.get("capital", 0)

        # --- Capital Update from Trades ---
        pnl_from_trades = 0
        for product, trades in state.own_trades.items():
            for trade in trades:
                pnl_from_trades -= trade.price * trade.quantity
                # print(f"Trade Executed: {product} {trade.quantity}@{trade.price}, Cash Flow: {-trade.price * trade.quantity:.2f}")
        current_capital += pnl_from_trades
        # print(f"PnL from trades this step: {pnl_from_trades:.2f}")

        # --- Initial Capital Setting ---
        if self.initial_capital is None:
            self.initial_capital = current_capital
            traderObject["initial_capital"] = self.initial_capital
            print(f"Initial Capital Set: {self.initial_capital:.2f}")

        profit = current_capital - self.initial_capital
        traderObject["capital"] = current_capital

        """
        # --- Stop Trading Check ---
        stop_trading = current_capital >= self.capital_stop_limit \
                       or current_capital <= self.max_drawdown \
                       or (self.initial_capital is not None and profit >= self.max_profit_limit)

        print(f"Timestamp: {state.timestamp}, Profit: {profit:.2f}, Capital: {current_capital:.2f}, Stop Trading: {stop_trading}")
        """
        # --- Main Trading Logic Loop ---
        for product in self.params:
            if product not in state.order_depths:
                continue

            orders: list[Order] = []
            position = state.position.get(product, 0)
            order_depth = state.order_depths[product]
            p = self.params[product]
            buy_volume = sell_volume = 0
            position_limit = self.LIMIT[product]

            # --- Calculations (Mid Price, Fair Value (Mean), Volatility) ---
            fair_value = p.get("fair_value", None) # Use static if needed, but prefer dynamic
            volatility = 0
            mid_price = None
            best_bid = None
            best_ask = None

            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid = max(order_depth.buy_orders)
                best_ask = min(order_depth.sell_orders)
                mid_price = (best_bid + best_ask) / 2
                self.mid_price_history[product].append(mid_price)
                if len(self.mid_price_history[product]) >= 2:
                    volatility = np.std(self.mid_price_history[product])
                # Always use dynamic fair value if history is available
                fair_value = np.mean(self.mid_price_history[product])
                # print(f"{product} - Mid: {mid_price:.2f}, Fair: {fair_value:.2f}, Vol: {volatility:.2f}")
            elif len(self.mid_price_history[product]) > 0:
                 # Use history mean if order book is thin but history exists
                 fair_value = np.mean(self.mid_price_history[product])
                 print(f"{product} - Thin book, using historical Fair Value: {fair_value:.2f}")

            """
            # --- Stop Trading Logic ---
            if stop_trading:
                if position != 0:
                    print(f"STOP TRADING TRIGGERED: Clearing position for {product}")
                    # Use the calculated fair_value (mean) for clearing reference if possible
                    clear_ref_price = fair_value if fair_value is not None else p.get("fair_value", mid_price) # Fallback logic
                    if clear_ref_price is not None:
                         b, s = self.clear_position(product, clear_ref_price, p["clear_width"], orders, order_depth, position)
                         buy_volume += b
                         sell_volume += s
                    else:
                         print(f"WARNING: Cannot determine clear price for {product}")
                else:
                    print(f"STOP TRADING TRIGGERED: No position for {product}")
                result[product] = orders
                continue # Skip normal trading logic for this product
             """
            # --- Product-Specific Trading Logic ---

            # ** SQUID_INK Mean Reversion Strategy **
            if product == Product.SQUID_INK:
                deviation = 0
                if mid_price is not None and fair_value is not None and volatility > 0.1: # Avoid division by zero or tiny vol
                    deviation = (mid_price - fair_value) / volatility # Z-score like measure
                    print(f"SQUID_INK Deviation (Z-score): {deviation:.2f}")

                entry_threshold = p["deviation_entry_threshold"]
                exit_threshold = p["deviation_exit_threshold"]

                # --- Exit Logic ---
                # If holding LONG and price reverted towards mean (deviation no longer very negative)
                if position > 0 and deviation > -exit_threshold:
                    qty_to_sell = position # Clear entire position
                    sell_price = best_bid if best_bid is not None else round(fair_value) # Sell aggressively
                    print(f"SQUID_INK EXIT LONG: Selling {qty_to_sell} near {sell_price}")
                    orders.append(Order(product, sell_price, -qty_to_sell))
                    sell_volume += qty_to_sell
                # If holding SHORT and price reverted towards mean (deviation no longer very positive)
                elif position < 0 and deviation < exit_threshold:
                    qty_to_buy = -position # Clear entire position
                    buy_price = best_ask if best_ask is not None else round(fair_value) # Buy aggressively
                    print(f"SQUID_INK EXIT SHORT: Buying {qty_to_buy} near {buy_price}")
                    orders.append(Order(product, buy_price, qty_to_buy))
                    buy_volume += qty_to_buy

                # --- Entry Logic (Only if not already exiting) ---
                elif buy_volume == 0 and sell_volume == 0: # Don't enter if we just exited
                    # If deviation is very negative (price below mean) -> BUY
                    if deviation < -entry_threshold:
                        qty_to_buy = position_limit - position # Buy up to limit
                        if qty_to_buy > 0:
                            buy_price = best_ask if best_ask is not None else round(fair_value + 1) # Aggressive buy price
                            print(f"SQUID_INK ENTRY LONG: Buying {qty_to_buy} near {buy_price} (Dev: {deviation:.2f})")
                            orders.append(Order(product, buy_price, qty_to_buy))
                            buy_volume += qty_to_buy
                    # If deviation is very positive (price above mean) -> SELL
                    elif deviation > entry_threshold:
                        qty_to_sell = position_limit + position # Sell up to limit (position is negative)
                        if qty_to_sell > 0:
                            sell_price = best_bid if best_bid is not None else round(fair_value - 1) # Aggressive sell price
                            print(f"SQUID_INK ENTRY SHORT: Selling {qty_to_sell} near {sell_price} (Dev: {deviation:.2f})")
                            orders.append(Order(product, sell_price, -qty_to_sell))
                            sell_volume += qty_to_sell

            # ** Standard Strategy for other products (RAINFOREST_RESIN, KELP) **
            else:
                # Dynamic Take Width for KELP
                if product == Product.KELP:
                     dynamic_take_width = max(10, volatility * 1.5) if volatility > 0 else p["take_width"]
                else:
                     dynamic_take_width = p["take_width"]

                # Aggressive Orders
                b, s = self.take_best_orders(product, fair_value, dynamic_take_width, orders, order_depth, position)
                buy_volume += b
                sell_volume += s
                # Market Making Orders
                b, s = self.make_orders(
                    product, order_depth, fair_value, position, buy_volume, sell_volume,
                    p["disregard_edge"], p["join_edge"], p["default_edge"],
                    True, p["soft_position_limit"]
                )
                buy_volume += b
                sell_volume += s

            result[product] = orders

        # --- State Persistence ---
        traderData = jsonpickle.encode(traderObject)
        conversions = 1
        return result, conversions, traderData

