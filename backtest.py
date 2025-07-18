import configparser
from datetime import datetime, timedelta
import importlib
import sys

from core.backtest_engine import BacktestEngine
from gateclient.client import GateIOClient


def get_strategy_class(strategy_name: str):
    """
    根据策略名称动态加载策略类。
    """
    try:
        module_path, class_name = strategy_name.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        print(f"错误: 无法加载策略 '{strategy_name}'. {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """
    回测程序主入口。
    """
    print("--- 交互式量化策略回测程序 ---")

    # --- 1. 获取并验证交易对 ---
    try:
        token_symbol = (
            input("第一步: 请输入您想回测的代币 (例如: BTC, SOL, ETH): ")
            .strip()
            .upper()
        )
        if not token_symbol:
            print("错误: 代币名称不能为空。", file=sys.stderr)
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n操作已取消。")
        sys.exit(0)

    trading_pair = f"{token_symbol}_USDT"

    print(f"正在验证交易对 '{trading_pair}' 是否存在于 Gate.io...")
    client = GateIOClient()
    if not client.check_currency_pair_exists(trading_pair):
        print(
            f"错误: 交易对 '{trading_pair}' 在 Gate.io 上不存在或无法查询。",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"验证成功！将针对 '{trading_pair}' 进行回测。")

    # --- 2. 获取并验证回测周期 ---
    try:
        days_to_backtest_str = input(
            "第二步: 请输入您想回测的天数 (例如: 30, 60, 120): "
        ).strip()
        if not days_to_backtest_str.isdigit():
            print("错误: 天数必须是一个正整数。", file=sys.stderr)
            sys.exit(1)
        days_to_backtest = int(days_to_backtest_str)
        if days_to_backtest <= 0:
            print("错误: 天数必须大于 0。", file=sys.stderr)
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n操作已取消。")
        sys.exit(0)

    print(f"目标回测周期设置为 {days_to_backtest} 天。")

    # --- 回测参数配置 ---
    INITIAL_CAPITAL = 500.0  # 初始资金 (USDT)
    END_DATE = datetime.utcnow()
    START_DATE = END_DATE - timedelta(days=days_to_backtest)

    # --- 加载通用配置 ---
    config = configparser.ConfigParser()
    config.read("config.ini")

    # 从配置中获取要使用的策略
    strategy_name = config.get("Strategy", "name", fallback=None)
    if not strategy_name:
        print("错误: 未在 config.ini 的 [Strategy] 段中配置 'name'。", file=sys.stderr)
        sys.exit(1)

    # 获取策略的特定配置，但会覆盖掉交易对
    strategy_config_section = f"Strategy.{strategy_name.split('.')[-1]}"
    if strategy_config_section in config:
        strategy_config = dict(config[strategy_config_section])
    else:
        strategy_config = {}

    # 使用用户输入的交易对，覆盖掉配置文件中的
    strategy_config["trading_pair"] = trading_pair

    StrategyClass = get_strategy_class(strategy_name)
    if not StrategyClass:
        sys.exit(1)

    # --- 运行回测 ---
    print("\n--- 准备启动回测引擎 ---")
    backtest = BacktestEngine(
        start_date=START_DATE,
        end_date=END_DATE,
        initial_capital=INITIAL_CAPITAL,
        strategy_class=StrategyClass,
        strategy_config=strategy_config,
        client=client,
    )

    backtest.run()


if __name__ == "__main__":
    main()
