# trading_bot.py (Version with Dynamic Fair Value and PnL Exit)

from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import jsonpickle
import numpy as np
import collections # Added for deque

class Product:
    RAINFOREST_RESIN = "RAINFOREST_RESIN"
    KELP = "KELP"
    SQUID_INK = "SQUID_INK"

PARAMS = {
    Product.RAINFOREST_RESIN: {
        "fair_value": 10000, # Will be updated dynamically
        "take_width": 2,
        "clear_width": 0.5,
        "disregard_edge": 3,
        "join_edge": 1,
        "default_edge": 2,
        "soft_position_limit": 25,
        "volatility_window": 10, # Window for volatility calculation
    },
    Product.KELP: {
        "fair_value": 2030, # Will be updated dynamically
        "take_width": 15, # This will be updated dynamically based on volatility
        "clear_width": 5,
        "disregard_edge": 25,
        "join_edge": 10,
        "default_edge": 20,
        "soft_position_limit": 30,
        "volatility_window": 10, # Window for volatility calculation
    },
    Product.SQUID_INK: {
        "fair_value": 1968, # Will be updated dynamically
        "take_width": 30,
        "clear_width": 10,
        "disregard_edge": 50,
        "join_edge": 20,
        "default_edge": 40,
        "soft_position_limit": 30,
        "volatility_window": 10, # Window for volatility calculation
    },
}

class Trader:
    def __init__(self):
        """
        Initializes the Trader class, setting up parameters, limits, and data structures.
        """
        self.params = PARAMS
        self.LIMIT = {p: 50 for p in PARAMS} # Position limit per product
        self.max_drawdown = -500 # Maximum allowed drawdown
        self.capital_stop_limit = 500 # Upper capital limit (consider if needed with profit target)
        # *** MODIFICATION: Set profit target to 1400 ***
        self.max_profit_limit = 1400 # Maximum profit target limit
        # Use deque for efficient rolling window operations
        self.mid_price_history = {product: collections.deque(maxlen=p["volatility_window"]) for product, p in PARAMS.items()}
        self.min_spread = 1 # Minimum spread required to market make

        # Variables to store state between runs
        self.initial_capital = None # Will be set on the first run

    def calculate_profit(self, state: TradingState, traderObject: Dict) -> float:
        """
        Calculates the current profit based on stored initial capital.
        Needs accurate capital tracking based on executed trades.
        """
        # *** IMPORTANT: Replace placeholder logic with actual PnL calculation ***
        # This requires tracking filled orders from the previous state (state.own_trades, state.market_trades)
        # and calculating the change in portfolio value + cash.
        # The 'capital' variable below is just a placeholder representation.
        # You need to implement the logic to update it based on trade executions.

        current_capital = traderObject.get("capital", 0) # Get current capital from state
        # Placeholder: Increment capital - REMOVE THIS IN ACTUAL IMPLEMENTATION
        # current_capital += 0 # Replace with actual PnL update logic

        # Store initial capital on the very first run
        if self.initial_capital is None:
            # Try to load initial capital if it exists in traderData
            self.initial_capital = traderObject.get("initial_capital")
            if self.initial_capital is None:
                 # If still None, set it to the current capital (first run)
                 self.initial_capital = current_capital
                 traderObject["initial_capital"] = self.initial_capital # Store it

        profit = current_capital - self.initial_capital
        traderObject["capital"] = current_capital # Store updated capital back
        return profit

    def take_best_orders(self, product, fair_value, take_width, orders, order_depth, position):
        """
        Places aggressive orders if the best bid/ask is significantly beyond the fair value.
        """
        position_limit = self.LIMIT[product]
        buy_volume = sell_volume = 0

        # Don't place orders if already at position limit
        if abs(position) >= position_limit:
            return 0, 0

        # Check best ask (potential buy)
        if order_depth.sell_orders:
            best_ask = min(order_depth.sell_orders)
            ask_volume = -order_depth.sell_orders[best_ask] # Sell orders have negative volume
            # If best ask is below fair value minus take width (attractive buy)
            if best_ask <= fair_value - take_width:
                qty = min(ask_volume, position_limit - position) # Buy up to limit
                if qty > 0:
                    print(f"TAKE BUY: {product} {qty}@{best_ask}")
                    orders.append(Order(product, best_ask, qty))
                    buy_volume += qty

        # Check best bid (potential sell)
        if order_depth.buy_orders:
            best_bid = max(order_depth.buy_orders)
            bid_volume = order_depth.buy_orders[best_bid]
            # If best bid is above fair value plus take width (attractive sell)
            if best_bid >= fair_value + take_width:
                qty = min(bid_volume, position_limit + position) # Sell up to limit (position is negative for short)
                if qty > 0:
                    print(f"TAKE SELL: {product} {qty}@{best_bid}")
                    orders.append(Order(product, best_bid, -qty)) # Sell order has negative quantity
                    sell_volume += qty

        return buy_volume, sell_volume

    def market_make(self, product, orders, bid, ask, position, buy_volume, sell_volume, order_depth):
        """
        Places passive limit buy and sell orders around the calculated bid/ask prices.
        """
        # Check minimum spread condition
        if order_depth.buy_orders and order_depth.sell_orders:
            best_bid_market = max(order_depth.buy_orders)
            best_ask_market = min(order_depth.sell_orders)
            if best_ask_market - best_bid_market < self.min_spread:
                 print(f"SPREAD TOO TIGHT: {product} ({best_ask_market - best_bid_market}), skipping market make.")
                 return buy_volume, sell_volume # Skip market making if spread is too tight

        # Calculate remaining capacity to buy/sell up to the limit
        buy_qty = self.LIMIT[product] - (position + buy_volume)
        if buy_qty > 0:
            # print(f"MM BUY: {product} {buy_qty}@{bid}")
            orders.append(Order(product, bid, buy_qty))

        sell_qty = self.LIMIT[product] + (position - sell_volume) # position is negative for short
        if sell_qty > 0:
            # print(f"MM SELL: {product} {sell_qty}@{ask}")
            orders.append(Order(product, ask, -sell_qty)) # Sell order has negative quantity

        return buy_volume, sell_volume

    def clear_position(self, product, fair_value, width, orders, order_depth, position):
        """
        Attempts to clear existing positions by placing orders within the clear_width.
        """
        buy_volume = sell_volume = 0
        # Define prices for clearing orders
        fair_bid = round(fair_value - width)
        fair_ask = round(fair_value + width)

        # If long position, try to sell
        if position > 0:
            # Check volume available at or above the clearing ask price
            clear_qty = sum(vol for price, vol in order_depth.buy_orders.items() if price >= fair_ask)
            clear_qty = min(clear_qty, position) # Can only clear up to the current position
            if clear_qty > 0:
                print(f"CLEAR SELL: {product} {clear_qty}@{fair_ask}")
                orders.append(Order(product, fair_ask, -clear_qty)) # Sell order
                sell_volume += clear_qty

        # If short position, try to buy
        elif position < 0:
            # Check volume available at or below the clearing bid price
            clear_qty = sum(-vol for price, vol in order_depth.sell_orders.items() if price <= fair_bid) # Sell orders have negative volume
            clear_qty = min(clear_qty, -position) # Can only clear up to the current position size
            if clear_qty > 0:
                print(f"CLEAR BUY: {product} {clear_qty}@{fair_bid}")
                orders.append(Order(product, fair_bid, clear_qty)) # Buy order
                buy_volume += clear_qty

        return buy_volume, sell_volume

    def make_orders(self, product, order_depth, fair_value, position, buy_volume, sell_volume, disregard_edge, join_edge, default_edge, manage_position, soft_position_limit):
        """
        Determines bid/ask prices for market making and calls market_make.
        Adjusts bid/ask based on position relative to soft limits.
        """
        orders = [] # Orders generated by this function specifically

        # Filter order book prices outside the disregard edge
        asks = [p for p in order_depth.sell_orders if p > fair_value + disregard_edge]
        bids = [p for p in order_depth.buy_orders if p < fair_value - disregard_edge]

        # Determine base ask price
        ask = round(fair_value + default_edge)
        if asks:
            best_ask = min(asks)
            # If the best ask outside disregard is close enough (within join_edge), join it, otherwise undercut slightly
            ask = best_ask if abs(best_ask - fair_value) <= join_edge else best_ask - 1

        # Determine base bid price
        bid = round(fair_value - default_edge)
        if bids:
            best_bid = max(bids)
            # If the best bid outside disregard is close enough (within join_edge), join it, otherwise overcut slightly
            bid = best_bid if abs(fair_value - best_bid) <= join_edge else best_bid + 1

        # Adjust bid/ask based on position management preference
        if manage_position:
            if position > soft_position_limit:
                ask -= 1 # Make selling slightly more attractive if too long
            elif position < -soft_position_limit:
                bid += 1 # Make buying slightly more attractive if too short

        # Place the market making orders
        return self.market_make(product, orders, bid, ask, position, buy_volume, sell_volume, order_depth)

    def run(self, state: TradingState) -> Dict[str, List[Order]]:
        """
        Main execution function called at each time step.
        Calculates state, determines trading actions, and places orders.
        """
        result = {}
        # Load persistent state data
        traderObject = jsonpickle.decode(state.traderData) if state.traderData else {}
        # Restore initial capital if it was set previously
        self.initial_capital = traderObject.get("initial_capital", self.initial_capital)

        # *** Calculate Profit & Loss ***
        # This needs to be based on actual PnL updates from executed trades
        profit = self.calculate_profit(state, traderObject) # Updates capital in traderObject

        # *** Determine if trading should stop ***
        current_capital = traderObject.get("capital", 0)
        stop_trading = current_capital >= self.capital_stop_limit \
                       or current_capital <= self.max_drawdown \
                       or (self.initial_capital is not None and profit >= self.max_profit_limit)

        print(f"Timestamp: {state.timestamp}, Profit: {profit:.2f}, Capital: {current_capital:.2f}, Stop Trading: {stop_trading}")

        # Iterate through each product defined in parameters
        for product in self.params:
            if product not in state.order_depths:
                continue # Skip if no market data for this product

            orders: list[Order] = []
            position = state.position.get(product, 0)
            order_depth = state.order_depths[product]
            p = self.params[product] # Parameters for the current product

            buy_volume = sell_volume = 0 # Track volume traded in this iteration

            # --- Calculate Mid Price and Volatility ---
            fair_value = p["fair_value"] # Start with static fair value
            volatility = 0
            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid = max(order_depth.buy_orders)
                best_ask = min(order_depth.sell_orders)
                mid_price = (best_bid + best_ask) / 2
                # Append to history (deque handles maxlen automatically)
                self.mid_price_history[product].append(mid_price)

                # Calculate volatility if enough history exists
                if len(self.mid_price_history[product]) >= 2: # Need at least 2 points for std dev
                    volatility = np.std(self.mid_price_history[product])

                # *** MODIFICATION: Dynamic Fair Value Calculation ***
                # Use the mean of the history as the dynamic fair value
                fair_value = np.mean(self.mid_price_history[product])
                # print(f"{product} - Mid: {mid_price:.2f}, Fair: {fair_value:.2f}, Vol: {volatility:.2f}")


            # --- Dynamic Parameter Adjustments (Example for KELP Take Width) ---
            # Adjust KELP take width based on volatility
            if product == Product.KELP:
                 dynamic_take_width = max(10, volatility * 1.5) # Example adjustment
                 # print(f"KELP Dynamic Take Width: {dynamic_take_width:.2f}")
            else:
                 dynamic_take_width = p["take_width"]

            # *** SUGGESTION: Add volatility adjustments for SQUID_INK here ***
            # Example: Adjust default_edge based on volatility for SQUID_INK
            # if product == Product.SQUID_INK:
            #     dynamic_default_edge = max(p["default_edge"], volatility * X) # X is a factor to tune
            #     dynamic_take_width = max(Y, volatility * Z) # Y, Z are factors to tune
            # else:
            #     dynamic_default_edge = p["default_edge"]
            # Use dynamic_default_edge and dynamic_take_width below instead of p["..."]


            # --- Trading Logic ---
            if not stop_trading:
                # 1. Aggressive Orders (Take Best)
                # *** SUGGESTION: Consider disabling this for SQUID_INK in high volatility ***
                # if not (product == Product.SQUID_INK and volatility > SOME_THRESHOLD):
                b, s = self.take_best_orders(product, fair_value, dynamic_take_width, orders, order_depth, position)
                buy_volume += b
                sell_volume += s

                # 2. Market Making Orders
                # *** SUGGESTION: Consider adjusting limits/edges for SQUID_INK based on volatility ***
                # Use dynamic_default_edge if implemented above
                b, s = self.make_orders(
                    product, order_depth, fair_value, position, buy_volume, sell_volume,
                    p["disregard_edge"], p["join_edge"], p["default_edge"], # Replace default_edge with dynamic if needed
                    True, p["soft_position_limit"] # Consider adjusting soft_position_limit based on vol
                )
                buy_volume += b
                sell_volume += s

            # 3. Clear Positions if stop_trading is True
            else:
                print(f"STOP TRADING TRIGGERED: Clearing position for {product}")
                b, s = self.clear_position(product, fair_value, p["clear_width"], orders, order_depth, position)
                buy_volume += b
                sell_volume += s

            result[product] = orders # Store orders for this product

        # --- State Persistence ---
        # Store updated state variables (capital, initial capital, history)
        # Note: mid_price_history is updated in place (deque)
        traderObject["initial_capital"] = self.initial_capital # Ensure it's stored
        # 'capital' was updated within calculate_profit
        traderData = jsonpickle.encode(traderObject)

        conversions = 1 # Default conversion value

        return result, conversions, traderData
