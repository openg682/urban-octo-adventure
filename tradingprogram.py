from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List
import json
import numpy as np

# Define ResinStrategy class outside the Trader class
class ResinStrategy:
    def __init__(self):
        self.history = []
        self.max_len = 10
        self.pos_limit = 50
        self.trade_volume = 30
        self.trigger_threshold = 2

    def update(self, mid_price):
        self.history.append(mid_price)
        if len(self.history) > self.max_len:
            self.history = self.history[-self.max_len:]

    def generate_orders(self, order_depth, current_position):
        if len(self.history) < self.max_len:
            return []

        avg_price = sum(self.history) / len(self.history)
        current_price = (max(order_depth.buy_orders.keys()) + min(order_depth.sell_orders.keys())) / 2
        deviation = current_price - avg_price

        orders = []
        # Go long if price is under mean by at least 2
        if deviation <= -self.trigger_threshold and current_position + self.trade_volume <= self.pos_limit:
            best_ask = min(order_depth.sell_orders.keys())
            volume = min(-order_depth.sell_orders[best_ask], self.pos_limit - current_position, self.trade_volume)
            if volume > 0:
                orders.append(Order("RAINFOREST_RESIN", best_ask, volume))

        # Go short if price is above mean by at least 2
        if deviation >= self.trigger_threshold and current_position - self.trade_volume >= -self.pos_limit:
            best_bid = max(order_depth.buy_orders.keys())
            volume = min(order_depth.buy_orders[best_bid], current_position + self.pos_limit, self.trade_volume)
            if volume > 0:
                orders.append(Order("RAINFOREST_RESIN", best_bid, -volume))

        return orders


class Trader:
    def run(self, state: TradingState):
        # Configurations
        max_pos = 50
        short_span = 10
        long_span = 50
        vol_window = 20
        volatility_threshold = 0.004  # 0.4%
        trend_threshold = 0.1  # Minimum EMA spread to act

        # List of products to trade
        all_products = ["KELP", "SQUID_INK", "RAINFOREST_RESIN"]
        trader_data = json.loads(state.traderData) if state.traderData else {}

        result_orders = {}

        # Helper function for EMA calculation
        def compute_ema(series, span):
            alpha = 2 / (span + 1)
            ema = series[0]
            for price in series[1:]:
                ema = alpha * price + (1 - alpha) * ema
            return ema

        # Initialize ResinStrategy
        resin_strategy = ResinStrategy()

        # Define price ranges for KELP and SQUID_INK
        kelp_price_range = (1990, 2050)  # KELP should stay between 2015 ± 15
        squid_ink_price_range = (1800, 2200)  # SQUID_INK should stay between 2000 ± 100

        # Iterate over each product and execute trading logic
        for product in all_products:
            # Initialize history if needed
            if product not in trader_data:
                trader_data[product] = {"prices": []}

            orders = []
            order_depth: OrderDepth = state.order_depths.get(product, None)
            if not order_depth or not order_depth.buy_orders or not order_depth.sell_orders:
                result_orders[product] = []
                continue

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            mid_price = (best_bid + best_ask) / 2

            # Append to price history
            prices = trader_data[product]["prices"]
            prices.append(mid_price)

            # Keep price history within the necessary window length
            max_len = max(long_span, vol_window) + 5
            if len(prices) > max_len:
                prices = prices[-max_len:]
            trader_data[product]["prices"] = prices

            position = state.position.get(product, 0)

            # Logic for RAINFOREST_RESIN using ResinStrategy
            if product == "RAINFOREST_RESIN":
                resin_strategy.update(mid_price)
                orders.extend(resin_strategy.generate_orders(order_depth, position))

            # Logic for KELP and SQUID_INK using price ranges and standard deviations
            elif product == "KELP":
                # Calculate the mean and standard deviation of the price history for KELP
                mean_price = np.mean(prices)
                std_dev = np.std(prices)

                # Calculate upper and lower price thresholds (±1 standard deviation)
                upper_threshold = mean_price + std_dev
                lower_threshold = mean_price - std_dev

                # Check if KELP price is above or below the thresholds to decide on buying/selling
                if mid_price <= lower_threshold and position + max_pos <= max_pos:
                    volume = min(-order_depth.sell_orders[best_ask], max_pos - position)
                    if volume > 0:
                        orders.append(Order("KELP", best_ask, volume))
                elif mid_price >= upper_threshold and position - max_pos >= -max_pos:
                    volume = min(order_depth.buy_orders[best_bid], position + max_pos)
                    if volume > 0:
                        orders.append(Order("KELP", best_bid, -volume))

            elif product == "SQUID_INK":
                # Calculate the mean and standard deviation of the price history for SQUID_INK
                mean_price = np.mean(prices)
                std_dev = np.std(prices)

                # Calculate upper and lower price thresholds (±1 standard deviation)
                upper_threshold = mean_price + std_dev
                lower_threshold = mean_price - std_dev

                # Check if SQUID_INK price is above or below the thresholds to decide on buying/selling
                if mid_price <= lower_threshold and position + max_pos <= max_pos:
                    volume = min(-order_depth.sell_orders[best_ask], max_pos - position)
                    if volume > 0:
                        orders.append(Order("SQUID_INK", best_ask, volume))
                elif mid_price >= upper_threshold and position - max_pos >= -max_pos:
                    volume = min(order_depth.buy_orders[best_bid], position + max_pos)
                    if volume > 0:
                        orders.append(Order("SQUID_INK", best_bid, -volume))

            result_orders[product] = orders

        return result_orders, 1, json.dumps(trader_data)
