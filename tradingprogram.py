from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List
import json
import numpy as np

class Trader:
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
        resin_strategy = self.ResinStrategy()

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

            # Logic for KELP
            elif product == "KELP":
                if kelp_price_range[0] <= mid_price <= kelp_price_range[1]:
                    if len(prices) >= long_span:
                        prices_np = np.array(prices)

                        # Calculate short-term and long-term EMAs
                        ema_short = compute_ema(prices_np[-short_span:], short_span)
                        ema_long = compute_ema(prices_np[-long_span:], long_span)
                        momentum = (prices_np[-1] - prices_np[-2]) / prices_np[-2]

                        # Calculate volatility
                        if len(prices_np) >= vol_window + 1:
                            returns = np.diff(prices_np[-(vol_window+1):]) / prices_np[-(vol_window+1):-1]
                            volatility = np.std(returns)
                        else:
                            volatility = 0

                        # Trading logic
                        ema_diff = abs(ema_short - ema_long)
                        buy_signal = (ema_short > ema_long and 
                                      momentum > 0 and 
                                      volatility < volatility_threshold and 
                                      ema_diff > trend_threshold)
                        sell_signal = (ema_short < ema_long and 
                                       momentum < 0 and 
                                       volatility < volatility_threshold and 
                                       ema_diff > trend_threshold)

                        if buy_signal:
                            available_volume = min(-order_depth.sell_orders[best_ask], max_pos - position)
                            if available_volume > 0:
                                orders.append(Order(product, best_ask, available_volume))

                        if sell_signal:
                            available_volume = min(order_depth.buy_orders[best_bid], position + max_pos)
                            if available_volume > 0:
                                orders.append(Order(product, best_bid, -available_volume))
                else:
                    print(f"KELP: Price {mid_price} is outside the allowed range.")

            # Logic for SQUID_INK
            elif product == "SQUID_INK":
                if squid_ink_price_range[0] <= mid_price <= squid_ink_price_range[1]:
                    if len(prices) >= long_span:
                        prices_np = np.array(prices)

                        # Calculate short-term and long-term EMAs
                        ema_short = compute_ema(prices_np[-short_span:], short_span)
                        ema_long = compute_ema(prices_np[-long_span:], long_span)
                        momentum = (prices_np[-1] - prices_np[-2]) / prices_np[-2]

                        # Calculate volatility
                        if len(prices_np) >= vol_window + 1:
                            returns = np.diff(prices_np[-(vol_window+1):]) / prices_np[-(vol_window+1):-1]
                            volatility = np.std(returns)
                        else:
                            volatility = 0

                        # Trading logic
                        ema_diff = abs(ema_short - ema_long)
                        buy_signal = (ema_short > ema_long and 
                                      momentum > 0 and 
                                      volatility < volatility_threshold and 
                                      ema_diff > trend_threshold)
                        sell_signal = (ema_short < ema_long and 
                                       momentum < 0 and 
                                       volatility < volatility_threshold and 
                                       ema_diff > trend_threshold)

                        if buy_signal:
                            available_volume = min(-order_depth.sell_orders[best_ask], max_pos - position)
                            if available_volume > 0:
                                orders.append(Order(product, best_ask, available_volume))

                        if sell_signal:
                            available_volume = min(order_depth.buy_orders[best_bid], position + max_pos)
                            if available_volume > 0:
                                orders.append(Order(product, best_bid, -available_volume))
                else:
                    print(f"SQUID_INK: Price {mid_price} is outside the allowed range.")
            
            result_orders[product] = orders

        return result_orders, 1, json.dumps(trader_data)
