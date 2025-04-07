from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List, Dict
import json
import random

class Trader:

    def __init__(self):
        self.max_position = 50
        self.smoothing = 0.5  # EMA smoothing factor
        self.stop_loss_percentage = 0.05  # Stop loss at 5% loss
        self.take_profit_percentage = 0.10  # Take profit at 10% profit

    def run(self, state: TradingState):
        print("traderData: " + state.traderData)
        print("Observations: " + str(state.observations))

        result = {}
        total_capital = 0  # This will store the trader's total capital

        # Load EMA memory from previous run
        if state.traderData:
            ema_memory: Dict[str, float] = json.loads(state.traderData)
        else:
            ema_memory = {}

        # Compute the trader's total capital from positions
        for product, position in state.position.items():
            order_depth: OrderDepth = state.order_depths.get(product, None)
            if order_depth:
                best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else 0
                best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else 0
                # If we have a position, we calculate its market value
                if position > 0:
                    total_capital += best_ask * position  # Long position
                elif position < 0:
                    total_capital += best_bid * -position  # Short position

        print(f"Total Capital: {total_capital}")

        # Capital protection: Stop trading if capital exceeds the stop threshold
        if total_capital > 200:
            print("Capital exceeds 200, closing all positions and stopping trading.")
            
            # Close all positions (i.e., sell if we have a long position, buy if we have a short position)
            for product, position in state.position.items():
                order_depth: OrderDepth = state.order_depths.get(product, None)
                if order_depth:
                    orders = []
                    if position > 0:
                        # Close long position by selling at the best ask price
                        best_ask = min(order_depth.sell_orders.keys())
                        orders = [Order(product, best_ask, -position)]  # Sell all of our position
                        print(f"CLOSING LONG: SELL {position} @ {best_ask}")
                    elif position < 0:
                        # Close short position by buying at the best bid price
                        best_bid = max(order_depth.buy_orders.keys())
                        orders = [Order(product, best_bid, -position)]  # Buy back all of our position
                        print(f"CLOSING SHORT: BUY {position} @ {best_bid}")
                    result[product] = orders

            return result, 1, state.traderData  # Return the orders to close positions

        # Now we proceed with trading if capital is within acceptable range
        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []

            # Get current position
            position = state.position.get(product, 0)

            # Skip if no market depth
            if not order_depth.buy_orders or not order_depth.sell_orders:
                continue

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            mid_price = (best_bid + best_ask) / 2

            # Update EMA (Exponential Moving Average) for fair value
            if product in ema_memory:
                ema_price = (self.smoothing * mid_price) + (1 - self.smoothing) * ema_memory[product]
            else:
                ema_price = mid_price  # initialize EMA with the first price

            ema_memory[product] = ema_price
            print(f"{product} EMA fair value: {ema_price}")

            # Implement Stop-Loss and Take-Profit based on the entry price
            entry_price = ema_price  # Using EMA as the entry point

            # Implement BUY logic
            if best_ask < ema_price:
                buy_volume = min(state.order_depths[product].sell_orders[best_ask], self.max_position - position)
                if buy_volume > 0:
                    print(f"BUY {buy_volume} @ {best_ask}")
                    orders.append(Order(product, best_ask, buy_volume))

            # Implement SELL logic
            if best_bid > ema_price:
                sell_volume = min(state.order_depths[product].buy_orders[best_bid], position + self.max_position)
                if sell_volume > 0:
                    print(f"SELL {sell_volume} @ {best_bid}")
                    orders.append(Order(product, best_bid, -sell_volume))

            # Implement Stop-Loss and Take-Profit
            if position > 0:  # If we have a long position
                stop_loss_price = entry_price * (1 - self.stop_loss_percentage)
                take_profit_price = entry_price * (1 + self.take_profit_percentage)
                if best_bid <= stop_loss_price:
                    print(f"STOP-LOSS: SELL {position} @ {best_bid}")
                    orders.append(Order(product, best_bid, -position))
                elif best_bid >= take_profit_price:
                    print(f"TAKE-PROFIT: SELL {position} @ {best_bid}")
                    orders.append(Order(product, best_bid, -position))

            elif position < 0:  # If we have a short position
                stop_loss_price = entry_price * (1 + self.stop_loss_percentage)
                take_profit_price = entry_price * (1 - self.take_profit_percentage)
                if best_ask >= stop_loss_price:
                    print(f"STOP-LOSS: BUY {abs(position)} @ {best_ask}")
                    orders.append(Order(product, best_ask, abs(position)))
                elif best_ask <= take_profit_price:
                    print(f"TAKE-PROFIT: BUY {abs(position)} @ {best_ask}")
                    orders.append(Order(product, best_ask, abs(position)))

            result[product] = orders

        # Save EMA values as traderData
        traderData = json.dumps(ema_memory)
        conversions = 1
        return result, conversions, traderData


        # Save EMA values as traderData
        traderData = json.dumps(ema_memory)
        conversions = 1
        return result, conversions, traderData
