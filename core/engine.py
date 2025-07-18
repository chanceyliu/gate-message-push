import configparser
import importlib
from gateclient.client import GateIOClient
import threading
import os


class TradingEngine:
    """
    交易引擎，负责加载配置、初始化模块和驱动策略并发运行。
    """

    def __init__(self, config_path: str):
        """
        初始化交易引擎。
        :param config_path: 配置文件路径。
        """
        self.config = configparser.ConfigParser()
        # 确保能读取包含UTF-8字符的配置文件
        self.config.read(config_path, encoding="utf-8")

        # 加载 .env 文件
        env_path = self.config.get("DEFAULT", "env_path", fallback="gate_config.env")
        if os.path.exists(env_path):
            from dotenv import load_dotenv

            load_dotenv(dotenv_path=env_path)

        self.client = None
        self.strategies = []

    def initialize(self):
        """
        根据配置初始化所有组件。
        """
        print("交易引擎初始化开始...")

        # 1. 初始化 GateIO API 客户端
        # api_key 和 api_secret 直接从环境变量读取
        self.client = GateIOClient()
        print("API 客户端初始化成功。")

        # 2. 获取要使用的策略类
        strategy_name = self.config.get("Strategy", "name")
        try:
            module_path, class_name = strategy_name.rsplit(".", 1)
            module = importlib.import_module(module_path)
            strategy_class = getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            print(
                f"错误: 无法加载策略 '{strategy_name}'. 请检查 config.ini 中的路径是否正确。 {e}"
            )
            return

        # 3. 获取该策略的通用配置
        strategy_config_section = f"Strategy.{strategy_class.__name__}"
        strategy_base_config = {}
        if self.config.has_section(strategy_config_section):
            strategy_base_config = dict(self.config.items(strategy_config_section))

        # 4. 获取要监控的交易对列表
        currency_pairs_str = self.config.get("GateIO", "currency_pairs")
        currency_pairs = [pair.strip() for pair in currency_pairs_str.split(",")]

        print(f"将为以下交易对创建策略实例: {currency_pairs}")

        # 5. 为每个交易对创建并初始化一个策略实例
        for pair in currency_pairs:
            # 复制通用配置
            pair_specific_config = strategy_base_config.copy()
            # 为当前实例设置特定的交易对
            pair_specific_config["trading_pair"] = pair

            # 实例化策略
            strategy_instance = strategy_class(self.client, pair_specific_config)
            self.strategies.append(strategy_instance)
            print(f"策略 '{strategy_name}' 已为交易对 '{pair}' 创建实例。")

        print("所有策略实例创建完毕。")

    def run(self):
        """
        为每个策略实例启动一个独立的线程，并等待它们全部完成。
        """
        if not self.strategies:
            print("没有可运行的策略。")
            return

        print(f"\n交易引擎启动... 将为 {len(self.strategies)} 个策略实例启动独立线程。")

        threads = []
        for strategy in self.strategies:
            # target 设置为策略实例的 run 方法
            thread = threading.Thread(
                target=strategy.run, name=f"Strategy-{strategy.trading_pair}"
            )
            threads.append(thread)
            thread.start()  # 启动线程
            print(f"线程 '{thread.name}' 已启动。")

        try:
            # 等待所有线程执行完毕
            # 在我们的场景中，因为策略的run方法是无限循环，
            # 主线程会在这里阻塞，直到所有子线程因异常或手动中断而结束。
            for thread in threads:
                thread.join()
        except KeyboardInterrupt:
            print("\n[主线程] 检测到手动中断 (Ctrl+C)，正在请求所有策略线程停止...")
            # 注意：子线程中的 KeyboardInterrupt 需要在子线程的 run 方法中捕获。
            # 这里的中断信号通常只被主线程捕获。
            # 我们依赖子线程自己的异常处理或循环条件来终止。

        print("交易引擎已停止。")
