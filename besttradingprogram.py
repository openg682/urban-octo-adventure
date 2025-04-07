from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List, Dict
import json

class Trader:

    def run(self, state: TradingState):
        print("traderData: " + state.traderData)
        print("Observations: " + str(state.observations))

        result = {}
        max_position = 50
        smoothing = 0.5  # EMA alpha (you can tweak this)

        # Load EMA memory from previous run
        if state.traderData:
            ema_memory: Dict[str, float] = json.loads(state.traderData)
        else:
            ema_memory = {}

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

            # Update EMA
            if product in ema_memory:
                ema_price = (smoothing * mid_price) + (1 - smoothing) * ema_memory[product]
            else:
                ema_price = mid_price  # initialize EMA with first price

            ema_memory[product] = ema_price
            print(f"{product} EMA fair value: {ema_price}")

            # BUY logic
            if best_ask < ema_price:
                best_ask_amount = order_depth.sell_orders[best_ask]
                buy_volume = min(-best_ask_amount, max_position - position)
                if buy_volume > 0:
                    print(f"BUY {buy_volume} @ {best_ask}")
                    orders.append(Order(product, best_ask, buy_volume))

            # SELL logic
            if best_bid > ema_price:
                best_bid_amount = order_depth.buy_orders[best_bid]
                sell_volume = min(best_bid_amount, position + max_position)
                if sell_volume > 0:
                    print(f"SELL {sell_volume} @ {best_bid}")
                    orders.append(Order(product, best_bid, -sell_volume))

            result[product] = orders

        # Save EMA values as traderData
        traderData = json.dumps(ema_memory)
        conversions = 1
        return result, conversions, traderData


