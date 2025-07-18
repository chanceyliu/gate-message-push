import pandas as pd
from datetime import datetime
from gateclient.client import GateIOClient


class Portfolio:
    """
    模拟投资组合，负责管理资金、持仓和交易。
    """

    def __init__(self, initial_capital=1000.0, fee_rate=0.002):
        self.initial_capital = float(initial_capital)
        self.fee_rate = float(fee_rate)

        self.cash = self.initial_capital
        self.positions = {}  # {'BTC': 1.5, 'ETH': 10}
        self.trades = []

    def get_total_value(self, current_prices):
        """计算当前总市值"""
        total_value = self.cash
        for symbol, amount in self.positions.items():
            price_key = f"{symbol}_USDT"
            if price_key in current_prices:
                total_value += amount * current_prices[price_key]
        return total_value

    def execute_trade(self, timestamp, symbol, side, amount, price):
        """
        执行一笔交易并更新持仓和现金。
        :param symbol: e.g. 'BTC'
        :param side: 'buy' or 'sell'
        :param amount: 交易的基础货币数量
        :param price: 成交价格
        """
        cost = amount * price
        fee = cost * self.fee_rate

        if side == "buy":
            if self.cash < cost + fee:
                print("资金不足，无法执行买入")
                return False
            self.cash -= cost + fee
            self.positions[symbol] = self.positions.get(symbol, 0) + amount
        elif side == "sell":
            if self.positions.get(symbol, 0) < amount:
                print("持仓不足，无法执行卖出")
                return False
            self.cash += cost - fee
            self.positions[symbol] -= amount
            if self.positions[symbol] == 0:
                del self.positions[symbol]

        trade_record = {
            "timestamp": timestamp,
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": price,
            "fee": fee,
        }
        self.trades.append(trade_record)
        return True


class BacktestEngine:
    """
    回测引擎，负责整个回测流程的控制。
    """

    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float,
        strategy_class,
        strategy_config: dict,
        client: GateIOClient = None,
    ):
        """
        初始化回测引擎。
        """
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.strategy_class = strategy_class
        self.strategy_config = strategy_config

        # 如果没有外部传入 client，则自己创建一个
        self.client = client if client else GateIOClient()

        self.portfolio = Portfolio(
            initial_capital=self.initial_capital,
            fee_rate=self.strategy_config.get("fee_rate", 0.002),
        )
        self.strategy = None
        self.data = None

    def _prepare_data(self, interval="1h"):
        """
        准备回测所需的历史数据。
        """
        trading_pair = self.strategy_config.get("trading_pair")
        if not trading_pair:
            raise ValueError("策略配置中缺少 'trading_pair' 参数。")

        print(
            f"开始获取 {trading_pair} 从 {self.start_date.strftime('%Y-%m-%d')} 到 {self.end_date.strftime('%Y-%m-%d')} 的 {interval} 历史K线数据..."
        )
        self.data = self.client.get_historical_klines(
            trading_pair, interval, self.start_date, self.end_date
        )

        if self.data is None or self.data.empty:
            print("错误: 未能获取到任何历史数据，无法继续回测。")
            return False

    def run(self):
        """启动回测。"""
        print("--- 开始回测 ---")

        # 1. 准备数据
        kline_interval = self.strategy_config.get("kline_interval", "1h")
        self._prepare_data(interval=kline_interval)

        # 2. 初始化策略
        # 注意：这里我们传递一个 self (BacktestEngine的实例) 给策略，
        # 这样策略内部就可以通过 self.engine.buy() 等方式来通知引擎执行交易
        self.strategy = self.strategy_class(client=None, config=self.strategy_config)
        self.strategy.set_engine(self)

        # 3. 运行回测循环
        self._run_loop()

        # 4. 生成并打印报告
        self._generate_report()

    def _run_loop(self):
        """回测主循环，遍历历史数据。"""
        print("\n--- 正在运行策略... ---")
        # 遍历每一根K线
        for timestamp, kline in self.data.iterrows():
            # 策略需要一个dataframe输入，所以我们传递截止到当前时间点的所有数据
            # 使用 .copy() 避免 SettingWithCopyWarning
            historical_data_so_far = self.data.loc[:timestamp].copy()

            # 调用策略的 on_kline 方法
            self.strategy.on_kline(historical_data_so_far)

    def _get_portfolio_state_at(self, timestamp):
        """
        计算并返回在指定时间点的投资组合状态（现金和持仓）。
        这是一个辅助函数，主要用于生成报告。
        """
        cash = self.portfolio.initial_capital
        positions = {}  # symbol -> amount

        # 筛选出在指定时间点之前或当日发生的所有交易
        trades_before_ts = [
            t for t in self.portfolio.trades if t["timestamp"] <= timestamp
        ]

        for trade in trades_before_ts:
            symbol = trade["symbol"]
            amount = trade["amount"]
            price = trade["price"]
            cost = amount * price
            fee = trade["fee"]

            if trade["side"] == "buy":
                cash -= cost + fee
                positions[symbol] = positions.get(symbol, 0) + amount
            elif trade["side"] == "sell":
                cash += cost - fee
                positions[symbol] = positions.get(symbol, 0) - amount

        # 清理数量接近于0的持仓，避免浮点数精度问题
        positions = {s: a for s, a in positions.items() if a > 1e-9}

        return cash, positions

    def _generate_report(self):
        """生成并打印最终的回测报告，包含总体和月度数据。"""
        print("\n--- 回测结束，生成报告 ---")

        trading_pair = self.strategy_config.get("trading_pair")
        base_currency = trading_pair.split("_")[0]

        # 即使没有交易，也计算最终资产（等于初始资金）
        if not self.portfolio.trades:
            final_total_value = self.portfolio.initial_capital
        else:
            final_prices = {trading_pair: self.data["close"].iloc[-1]}
            final_total_value = self.portfolio.get_total_value(
                current_prices=final_prices
            )

        pnl = final_total_value - self.portfolio.initial_capital
        pnl_percent = (
            (pnl / self.portfolio.initial_capital) * 100
            if self.portfolio.initial_capital > 0
            else 0
        )

        print("\n======== 整体回测结果 ========")
        print(
            f"时间范围: {self.data.index[0].strftime('%Y-%m-%d')} 到 {self.data.index[-1].strftime('%Y-%m-%d')}"
        )
        print(f"交易对: {trading_pair}")
        print(f"初始资金: {self.portfolio.initial_capital:.2f} USDT")
        print(f"最终资产: {final_total_value:.2f} USDT")
        print(f"总盈亏: {pnl:.2f} USDT")
        print(f"收益率: {pnl_percent:.2f}%")
        print(f"总交易次数: {len(self.portfolio.trades)}")

        if not self.portfolio.trades:
            print("回测期间无交易。")
            print("==========================")
            return

        # --- 分段生成盈利报告 ---
        print("\n======== 分段盈利报告 ========")

        all_months = sorted(self.data.index.strftime("%Y-%m").unique())

        report_data = []
        last_period_end_value = self.portfolio.initial_capital

        for month_str in all_months:
            month_mask = self.data.index.strftime("%Y-%m") == month_str
            month_data = self.data.loc[month_mask]

            # 获取该时间段的开始和结束时间点
            start_of_period = month_data.index[0]
            end_of_period_kline = month_data.iloc[-1]
            end_of_period_timestamp = end_of_period_kline.name
            end_of_period_price = end_of_period_kline["close"]

            # 计算时间段末的总资产
            eop_cash, eop_positions = self._get_portfolio_state_at(
                end_of_period_timestamp
            )
            eop_holdings_value = (
                eop_positions.get(base_currency, 0) * end_of_period_price
            )
            eop_total_value = eop_cash + eop_holdings_value

            # 计算该时间段的盈亏
            pnl_for_period = eop_total_value - last_period_end_value

            # 统计该时间段的交易次数
            trades_in_period = len(
                [
                    t
                    for t in self.portfolio.trades
                    if start_of_period
                    <= pd.to_datetime(t["timestamp"])
                    <= end_of_period_timestamp
                ]
            )

            report_data.append(
                {
                    "时间段": f"{start_of_period.strftime('%Y-%m-%d')} to {end_of_period_timestamp.strftime('%Y-%m-%d')}",
                    "区间盈亏(USDT)": f"{pnl_for_period:+.2f}",
                    "期末总资产(USDT)": f"{eop_total_value:.2f}",
                    "区间交易次数": trades_in_period,
                }
            )

            last_period_end_value = eop_total_value

        report_df = pd.DataFrame(report_data)
        if not report_df.empty:
            print(report_df.to_string(index=False))

        print("==========================")

    # --- 策略与引擎交互的接口 ---
    def buy(self, symbol, timestamp, price, amount=None):
        """策略调用此方法来执行买入操作。"""
        # 简单起见，我们实现一个"全仓买入"的逻辑
        if amount is None:
            # 用99%的现金购买，留一些余地给手续费
            amount_to_buy = (self.portfolio.cash * 0.99) / price

        print(
            f"[{timestamp}] 引擎收到买入信号: 买入 {amount_to_buy:.4f} {symbol} @ {price:.2f}"
        )
        self.portfolio.execute_trade(timestamp, symbol, "buy", amount_to_buy, price)

    def sell(self, symbol, timestamp, price, amount=None):
        """策略调用此方法来执行卖出操作。"""
        # 简单起见，我们实现一个"全部卖出"的逻辑
        if amount is None:
            amount_to_sell = self.portfolio.positions.get(symbol, 0)

        if amount_to_sell > 0:
            print(
                f"[{timestamp}] 引擎收到卖出信号: 卖出 {amount_to_sell:.4f} {symbol} @ {price:.2f}"
            )
            self.portfolio.execute_trade(
                timestamp, symbol, "sell", amount_to_sell, price
            )
