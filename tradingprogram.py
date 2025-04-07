import numpy as np
import json
from datamodel import OrderDepth, TradingState, Order


class ResinStrategy:
    def __init__(self):
        self.history = []
        self.max_len = 20  # Increase history length for more accurate statistics
        self.pos_limit = 50
        self.trade_volume = 30
        self.trigger_threshold = 2
        self.volatility_window = 20  # Look-back window for volatility calculation
        self.entry_price = None  # To store the entry price for stop-loss and take-profit
        self.stop_loss_pct = 0.01  # 2% stop-loss
        self.take_profit_pct = 0.03  # 5% take-profit

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

        # Calculate standard deviation of recent prices for volatility
        std_dev = np.std(self.history[-self.volatility_window:])

        # Dynamic position sizing based on volatility
        dynamic_position = min(self.trade_volume, int(self.pos_limit / (std_dev + 1e-6)))  # Prevent division by zero

        # Set stop loss and take profit orders based on entry price
        orders = []

        # If we already have an entry price, let's check stop loss or take profit
        if self.entry_price is not None:
            if current_position > 0:  # Long position
                if current_price <= self.entry_price * (1 - self.stop_loss_pct):  # Trigger stop loss
                    orders.append(Order("RAINFOREST_RESIN", current_price, -current_position))
                elif current_price >= self.entry_price * (1 + self.take_profit_pct):  # Trigger take profit
                    orders.append(Order("RAINFOREST_RESIN", current_price, -current_position))

            elif current_position < 0:  # Short position
                if current_price >= self.entry_price * (1 + self.stop_loss_pct):  # Trigger stop loss
                    orders.append(Order("RAINFOREST_RESIN", current_price, -current_position))
                elif current_price <= self.entry_price * (1 - self.take_profit_pct):  # Trigger take profit
                    orders.append(Order("RAINFOREST_RESIN", current_price, -current_position))

        # If no position, we follow the strategy to enter a new position
        if self.entry_price is None:
            if deviation <= -self.trigger_threshold and current_position + dynamic_position <= self.pos_limit:
                best_ask = min(order_depth.sell_orders.keys())
                volume = min(-order_depth.sell_orders[best_ask], self.pos_limit - current_position, dynamic_position)
                if volume > 0:
                    orders.append(Order("RAINFOREST_RESIN", best_ask, volume))
                    self.entry_price = best_ask  # Set entry price for stop loss and take profit

            elif deviation >= self.trigger_threshold and current_position - dynamic_position >= -self.pos_limit:
                best_bid = max(order_depth.buy_orders.keys())
                volume = min(order_depth.buy_orders[best_bid], current_position + self.pos_limit, dynamic_position)
                if volume > 0:
                    orders.append(Order("RAINFOREST_RESIN", best_bid, -volume))
                    self.entry_price = best_bid  # Set entry price for stop loss and take profit

        return orders


class Trader:
    def run(self, state: TradingState):
        max_pos = 50
        short_span = 10
        long_span = 50
        vol_window = 20
        volatility_threshold = 0.004  # 0.4%
        trend_threshold = 0.1  # Minimum EMA spread to act

        all_products = ["KELP", "SQUID_INK", "RAINFOREST_RESIN"]
        trader_data = json.loads(state.traderData) if state.traderData else {}

        result_orders = {}

        def compute_ema(series, span):
            alpha = 2 / (span + 1)
            ema = series[0]
            for price in series[1:]:
                ema = alpha * price + (1 - alpha) * ema
            return ema

        resin_strategy = ResinStrategy()

        kelp_price_range = (1990, 2050)
        squid_ink_price_range = (1800, 2200)

        for product in all_products:
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

            prices = trader_data[product]["prices"]
            prices.append(mid_price)

            max_len = max(long_span, vol_window) + 5
            if len(prices) > max_len:
                prices = prices[-max_len:]
            trader_data[product]["prices"] = prices

            position = state.position.get(product, 0)

            # Logic for RAINFOREST_RESIN
            if product == "RAINFOREST_RESIN":
                resin_strategy.update(mid_price)
                orders.extend(resin_strategy.generate_orders(order_depth, position))

            # Logic for KELP and SQUID_INK using price ranges and standard deviations
            elif product == "KELP":
                mean_price = np.mean(prices)
                std_dev = np.std(prices)
                upper_threshold = mean_price + std_dev
                lower_threshold = mean_price - std_dev

                # Dynamic Position Size based on standard deviation
                dynamic_position = min(max_pos, int(std_dev * 10))  # Larger position for more volatility

                if mid_price <= lower_threshold and position + dynamic_position <= max_pos:
                    volume = min(-order_depth.sell_orders[best_ask], max_pos - position)
                    if volume > 0:
                        orders.append(Order("KELP", best_ask, volume))
                elif mid_price >= upper_threshold and position - dynamic_position >= -max_pos:
                    volume = min(order_depth.buy_orders[best_bid], position + max_pos)
                    if volume > 0:
                        orders.append(Order("KELP", best_bid, -volume))

            elif product == "SQUID_INK":
                mean_price = np.mean(prices)
                std_dev = np.std(prices)
                upper_threshold = mean_price + std_dev
                lower_threshold = mean_price - std_dev

                dynamic_position = min(max_pos, int(std_dev * 10))

                if mid_price <= lower_threshold and position + dynamic_position <= max_pos:
                    volume = min(-order_depth.sell_orders[best_ask], max_pos - position)
                    if volume > 0:
                        orders.append(Order("SQUID_INK", best_ask, volume))
                elif mid_price >= upper_threshold and position - dynamic_position >= -max_pos:
                    volume = min(order_depth.buy_orders[best_bid], position + max_pos)
                    if volume > 0:
                        orders.append(Order("SQUID_INK", best_bid, -volume))

            result_orders[product] = orders

        return result_orders, 1, json.dumps(trader_data)
