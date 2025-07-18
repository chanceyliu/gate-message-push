import time
import pandas as pd
import pandas_ta as ta
import configparser
from strategies.base_strategy import BaseStrategy
from gateclient.client import GateIOClient
from notifications.pushplus_client import PushPlusClient
import os


class MovingAverageStrategy(BaseStrategy):
    """
    均线交叉策略。
    - 当短期均线上穿长期均线（金叉），产生买入信号。
    - 当短期均线下穿长期均线（死叉），产生卖出信号。
    """

    def __init__(self, client: GateIOClient, config: dict = None):
        super().__init__(client, config)

        # 从配置中读取策略参数
        self.short_window = int(self.config.get("short_window", 5))
        self.long_window = int(self.config.get("long_window", 20))
        self.kline_interval = self.config.get("kline_interval", "1h")
        self.run_interval = int(self.config.get("run_interval", 60))

        # 新增：优化参数
        self.filter_window = int(self.config.get("filter_window", 100))
        self.stop_loss_pct = float(self.config.get("stop_loss_pct", 0.02))
        # self.take_profit_pct = float(self.config.get("take_profit_pct", 0.05)) # 被移动止盈替代
        self.trailing_stop_pct = float(self.config.get("trailing_stop_pct", 0.04))
        self.trailing_stop_callback_pct = float(
            self.config.get("trailing_stop_callback_pct", 0.01)
        )

        # 新增：MACD 和 RSI 参数
        self.macd_fast = int(self.config.get("macd_fast", 12))
        self.macd_slow = int(self.config.get("macd_slow", 26))
        self.macd_signal = int(self.config.get("macd_signal", 9))
        self.rsi_window = int(self.config.get("rsi_window", 14))
        self.rsi_overbought = int(self.config.get("rsi_overbought", 70))

        # 检查参数合法性
        if self.short_window >= self.long_window:
            raise ValueError("短期均线窗口必须小于长期均线窗口。")

        # 策略状态变量
        self.position = "none"  # 'none' or 'long'
        self.last_signal = "none"  # 'buy', 'sell', 'none' to avoid repeated signals
        self.entry_price = 0.0  # 记录买入价格
        self.highest_price_since_entry = 0.0  # 记录入场后的最高价，用于移动止盈
        self.last_simple_signal = (
            "none"  # 'golden', 'death', 'none' to avoid repeated simple signals
        )

        # 初始化 PushPlus 客户端
        # token 的值依赖于 .env 文件，该文件已由 TradingEngine 在启动时加载
        config_parser = configparser.ConfigParser()
        config_parser.read("config.ini", encoding="utf-8")

        pushplus_token = os.getenv("PUSHPLUS_TOKEN") or config_parser.get(
            "PushPlus", "token", fallback=None
        )

        if pushplus_token and pushplus_token.startswith("${"):
            pushplus_token = None  # 如果解析失败，则置为None

        self.pushplus_client = (
            PushPlusClient(token=pushplus_token) if pushplus_token else None
        )

        # 回测通知开关和标志位
        self.backtest_notify_enabled = config_parser.getboolean(
            "PushPlus", "backtest_notify_enabled", fallback=False
        )
        self.backtest_notification_sent = False

    def _process_indicators(self, klines_df: pd.DataFrame) -> pd.DataFrame:
        """
        计算所有需要的技术指标。
        """
        klines_df.ta.ema(
            length=self.short_window,
            append=True,
            col_names=(f"EMA_{self.short_window}",),
        )
        klines_df.ta.ema(
            length=self.long_window,
            append=True,
            col_names=(f"EMA_{self.long_window}",),
        )
        klines_df.ta.ema(
            length=self.filter_window,
            append=True,
            col_names=(f"EMA_{self.filter_window}",),
        )
        klines_df.ta.macd(
            fast=self.macd_fast,
            slow=self.macd_slow,
            signal=self.macd_signal,
            append=True,
        )
        klines_df.ta.rsi(length=self.rsi_window, append=True)

        klines_df.rename(
            columns={
                f"EMA_{self.short_window}": "short_ma",
                f"EMA_{self.long_window}": "long_ma",
                f"EMA_{self.filter_window}": "filter_ma",
                f"MACD_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}": "macd",
                f"MACDh_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}": "macd_hist",
                f"MACDs_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}": "macd_signal_line",
                f"RSI_{self.rsi_window}": "rsi",
            },
            inplace=True,
        )
        return klines_df

    def _check_buy_conditions(
        self, latest_kline: pd.Series, previous_kline: pd.Series, current_price: float
    ):
        """
        检查多重买入条件。
        返回: (是否买入: bool, 信号详情: dict)
        """
        # 条件1: 金叉
        is_golden_cross = (
            previous_kline["short_ma"] < previous_kline["long_ma"]
            and latest_kline["short_ma"] > latest_kline["long_ma"]
        )
        # 条件2: 长期趋势向上
        is_uptrend = current_price > latest_kline["filter_ma"]
        # 条件3: MACD看涨 (快线在信号线上方)
        is_macd_bullish = latest_kline["macd"] > latest_kline["macd_signal_line"]
        # 条件4: RSI未超买
        is_rsi_ok = latest_kline["rsi"] < self.rsi_overbought

        if is_golden_cross and is_uptrend and is_macd_bullish and is_rsi_ok:
            details = {
                "金叉": "是",
                "长期趋势": f"向上 (价格 {current_price:.4f} > 趋势MA {latest_kline['filter_ma']:.4f})",
                "MACD": f"看涨 (MACD {latest_kline['macd']:.4f} > 信号线 {latest_kline['macd_signal_line']:.4f})",
                "RSI": f"{latest_kline['rsi']:.2f} (未超买)",
            }
            return True, details
        return False, None

    def _check_sell_conditions(
        self, latest_kline: pd.Series, previous_kline: pd.Series, current_price: float
    ):
        """
        检查多重卖出条件（带优先级）。
        返回: (卖出原因: str, 卖出详情: str)
        """
        # 1. 固定止损条件
        stop_loss_price = self.entry_price * (1 - self.stop_loss_pct)
        if current_price <= stop_loss_price:
            sell_reason = "固定止损"
            sell_details = (
                f"入场价 `{self.entry_price:.4f}`, 止损触发价 `{stop_loss_price:.4f}`"
            )
            return sell_reason, sell_details

        # 2. 移动止盈条件
        if self.highest_price_since_entry >= self.entry_price * (
            1 + self.trailing_stop_pct
        ):
            trailing_stop_trigger_price = self.highest_price_since_entry * (
                1 - self.trailing_stop_callback_pct
            )
            if current_price <= trailing_stop_trigger_price:
                sell_reason = "移动止盈"
                sell_details = f"入场后最高价 `{self.highest_price_since_entry:.4f}`, 回调触发价 `{trailing_stop_trigger_price:.4f}`"
                return sell_reason, sell_details

        # 3. 死叉卖出条件
        is_death_cross = (
            previous_kline["short_ma"] > previous_kline["long_ma"]
            and latest_kline["short_ma"] < latest_kline["long_ma"]
        )
        if is_death_cross:
            sell_reason = "死叉卖出"
            sell_details = f"短MA从 {previous_kline['short_ma']:.4f} 下穿 长MA {previous_kline['long_ma']:.4f}"
            return sell_reason, sell_details

        return None, None

    def _check_and_notify_simple_crosses(
        self, latest_kline: pd.Series, previous_kline: pd.Series
    ):
        """
        检查并发送简单的金叉/死叉信号提醒（不执行交易）。
        """
        is_simple_golden_cross = (
            previous_kline["short_ma"] < previous_kline["long_ma"]
            and latest_kline["short_ma"] > latest_kline["long_ma"]
        )
        is_simple_death_cross = (
            previous_kline["short_ma"] > previous_kline["long_ma"]
            and latest_kline["short_ma"] < latest_kline["long_ma"]
        )

        current_price = latest_kline["close"]
        notification_sent = False

        if is_simple_golden_cross and self.last_simple_signal != "golden":
            self.last_simple_signal = "golden"
            if self.pushplus_client:
                title = f"信号提醒: {self.trading_pair} 出现金叉"
                content = (
                    f"## 交易对: {self.trading_pair}\n\n"
                    f"**信号类型**: 金叉信号 (仅提醒)\n\n"
                    f"**当前价格**: `{current_price:.4f}`\n\n"
                    f"**时间**: `{time.strftime('%Y-%m-%d %H:%M:%S')}`"
                )
                self.pushplus_client.send_notification(title, content)
                notification_sent = True

        elif is_simple_death_cross and self.last_simple_signal != "death":
            self.last_simple_signal = "death"
            if self.pushplus_client:
                title = f"信号提醒: {self.trading_pair} 出现死叉"
                content = (
                    f"## 交易对: {self.trading_pair}\n\n"
                    f"**信号类型**: 死叉信号 (仅提醒)\n\n"
                    f"**当前价格**: `{current_price:.4f}`\n\n"
                    f"**时间**: `{time.strftime('%Y-%m-%d %H:%M:%S')}`"
                )
                self.pushplus_client.send_notification(title, content)
                notification_sent = True

        if notification_sent:
            print(f"---【信号提醒】已发送 {self.last_simple_signal} 信号通知 ---")

    def run(self):
        """
        策略的主执行逻辑。
        """
        print(f"开始执行均线交叉策略: {self.trading_pair}")
        print(
            f"参数: short_window={self.short_window}, long_window={self.long_window}, "
            f"kline_interval={self.kline_interval}, run_interval={self.run_interval}s"
        )
        print(
            f"优化参数: filter_window={self.filter_window}, stop_loss_pct={self.stop_loss_pct}, "
            f"trailing_stop_pct={self.trailing_stop_pct}, trailing_stop_callback_pct={self.trailing_stop_callback_pct}"
        )
        print(
            f"指标参数: macd_fast={self.macd_fast}, macd_slow={self.macd_slow}, macd_signal={self.macd_signal}, "
            f"rsi_window={self.rsi_window}, rsi_overbought={self.rsi_overbought}"
        )

        try:
            while True:
                # 1. 获取 K 线数据
                klines_limit = self.filter_window + 50
                klines_df = self.client.get_klines(
                    currency_pair=self.trading_pair,
                    interval=self.kline_interval,
                    limit=klines_limit,
                )

                if klines_df is None or len(klines_df) < self.filter_window:
                    print(
                        f"K线数据不足 (需要 {self.filter_window}, 得到 {len(klines_df)})，等待下一周期..."
                    )
                    time.sleep(self.run_interval)
                    continue

                # 2. 计算所有技术指标
                klines_df = self._process_indicators(klines_df)

                # 获取最近的两条K线数据用于判断
                latest_kline = klines_df.iloc[-1]
                previous_kline = klines_df.iloc[-2]

                # 检查指标值是否有效
                required_cols = [
                    "short_ma",
                    "long_ma",
                    "filter_ma",
                    "macd",
                    "macd_signal_line",
                    "rsi",
                ]
                if pd.isna(latest_kline[required_cols]).any():
                    print("部分技术指标为 NaN，等待下一周期...")
                    time.sleep(self.run_interval)
                    continue

                current_price = latest_kline["close"]
                print(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"最新价: {current_price:.4f}, "
                    f"RSI: {latest_kline['rsi']:.2f}, "
                    f"仓位: {self.position}, "
                    f"上次信号: {self.last_simple_signal}"
                )

                # --- 3. 判断并执行交易 ---
                trade_executed = False

                # 3.1 判断卖出条件
                if self.position == "long":
                    sell_reason, sell_details = self._check_sell_conditions(
                        latest_kline, previous_kline, current_price
                    )
                    if sell_reason:
                        self.position = "none"
                        sell_price = current_price
                        print(
                            f"--- 【交易执行 - 卖出】{sell_reason}！价格 {sell_price:.4f} ---"
                        )
                        # TODO: 在此执行真实的卖出操作

                        if self.pushplus_client:
                            title = (
                                f"交易执行[卖出]: {self.trading_pair} ({sell_reason})"
                            )
                            content = (
                                f"## {sell_reason}: {self.trading_pair}\n\n"
                                f"**卖出价格**: `{sell_price:.4f}`\n\n"
                                f"**详情**: {sell_details}\n\n"
                                f"**时间**: `{time.strftime('%Y-%m-%d %H:%M:%S')}`"
                            )
                            self.pushplus_client.send_notification(title, content)

                        # 如果是因为死叉卖出，更新简单信号状态，防止重复提醒
                        if sell_reason == "死叉卖出":
                            self.last_simple_signal = "death"
                        trade_executed = True

                # 3.2 判断买入条件
                if self.position == "none" and not trade_executed:
                    is_buy, buy_details = self._check_buy_conditions(
                        latest_kline, previous_kline, current_price
                    )
                    if is_buy:
                        self.position = "long"
                        buy_price = current_price
                        self.entry_price = buy_price
                        self.highest_price_since_entry = buy_price  # 重置最高价

                        print(
                            f"---【交易执行 - 买入】多重信号！价格: {buy_price:.4f} ---"
                        )
                        # TODO: 在此执行真实的买入操作

                        if self.pushplus_client:
                            title = f"交易执行[买入]: {self.trading_pair} (多重信号)"
                            content = (
                                f"## 多重信号买入: {self.trading_pair}\n\n"
                                f"**买入价格**: `{buy_price:.4f}`\n\n"
                                f"**信号详情**:\n"
                                + "".join(
                                    [
                                        f"- {key}: `{value}`\n"
                                        for key, value in buy_details.items()
                                    ]
                                )
                                + f"\n**时间**: `{time.strftime('%Y-%m-%d %H:%M:%S')}`"
                            )
                            self.pushplus_client.send_notification(title, content)

                        # 买入基于金叉，更新简单信号状态，防止重复提醒
                        self.last_simple_signal = "golden"
                        trade_executed = True

                # --- 4. 检查并发送独立的简单信号提醒 ---
                if not trade_executed:
                    self._check_and_notify_simple_crosses(latest_kline, previous_kline)

                time.sleep(self.run_interval)

        except KeyboardInterrupt:
            print("\n策略执行被用户中断。")
        except Exception as e:
            print(f"策略执行过程中发生错误: {e}")
            import traceback

            traceback.print_exc()

    def on_kline(self, klines_df: pd.DataFrame):
        """
        回测模式下，由引擎在每个K线时间点调用。
        """
        # 1. 确保有足够数据计算均线和指标
        if len(klines_df) < self.filter_window:
            return

        # 2. 计算所有技术指标
        klines_df = self._process_indicators(klines_df)

        # 获取最近的两条K线数据用于判断
        latest_kline = klines_df.iloc[-1]
        previous_kline = klines_df.iloc[-2]

        # 检查指标值是否有效
        required_cols = [
            "short_ma",
            "long_ma",
            "filter_ma",
            "macd",
            "macd_signal_line",
            "rsi",
        ]
        if pd.isna(latest_kline[required_cols]).any():
            return

        # 3. 判断交易信号
        current_price = latest_kline["close"]
        current_position_amount = self.engine.portfolio.positions.get(
            self.base_currency, 0
        )

        # --- 判断卖出条件（优先级最高）---
        if current_position_amount > 0:
            # 更新入场后的最高价
            self.highest_price_since_entry = max(
                self.highest_price_since_entry, current_price
            )

            sell_reason, sell_details = self._check_sell_conditions(
                latest_kline, previous_kline, current_price
            )

            if sell_reason:
                print(f"---【{sell_reason}】价格: {current_price:.2f} ---")
                self.engine.sell(
                    self.base_currency, timestamp=latest_kline.name, price=current_price
                )
                self.last_signal = "sell"
                # 发送通知
                if (
                    self.pushplus_client
                    and self.backtest_notify_enabled
                    and not self.backtest_notification_sent
                ):
                    title = f"策略回测卖出信号: {self.trading_pair}"
                    content = (
                        f"## {sell_reason}: {self.trading_pair}\n\n"
                        f"**卖出价格**: `{current_price:.4f}`\n\n"
                        f"**详情**: {sell_details}\n\n"
                        f"**时间**: `{latest_kline.name.strftime('%Y-%m-%d %H:%M:%S')}`"
                    )
                    self.pushplus_client.send_notification(title, content)
                    self.backtest_notification_sent = True
                return

        # --- 判断买入条件 ---
        if current_position_amount == 0:
            is_buy, buy_details = self._check_buy_conditions(
                latest_kline, previous_kline, current_price
            )

            if is_buy:
                buy_price = current_price
                print(
                    f"---【多重信号买入】价格: {buy_price:.2f} (MA-UP, MACD-BULL, RSI-OK)"
                )
                self.engine.buy(
                    self.base_currency, timestamp=latest_kline.name, price=buy_price
                )
                self.last_signal = "buy"
                self.entry_price = buy_price
                self.highest_price_since_entry = buy_price  # 重置最高价

                # 发送 PushPlus 通知
                if (
                    self.pushplus_client
                    and self.backtest_notify_enabled
                    and not self.backtest_notification_sent
                ):
                    title = f"策略回测买入信号: {self.trading_pair}"
                    content = (
                        f"## 交易对: {self.trading_pair}\n\n"
                        f"**信号类型**: 多重信号买入 (回测)\n\n"
                        f"**买入价格**: `{buy_price:.4f}`\n\n"
                        f"**信号详情**:\n"
                        + "".join(
                            [
                                f"- {key}: `{value}`\n"
                                for key, value in buy_details.items()
                            ]
                        )
                        + f"\n**时间**: `{latest_kline.name.strftime('%Y-%m-%d %H:%M:%S')}`"
                    )
                    self.pushplus_client.send_notification(title, content)
                    self.backtest_notification_sent = True
