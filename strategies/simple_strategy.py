import time
from strategies.base_strategy import BaseStrategy
from gateclient.client import GateIOClient


class SimpleStrategy(BaseStrategy):
    """
    一个简单的示例策略。
    该策略会定期获取指定交易对的最新价格并打印出来。
    """

    def __init__(self, client: GateIOClient, config: dict = None):
        # 调用父类的构造函数
        super().__init__(client, config)
        # 从配置中获取轮询间隔，并转换为整数，如果没有则默认为 10 秒
        self.interval = int(self.config.get("interval", 10))

    def run(self):
        """
        策略的主执行逻辑。
        """
        print(f"开始执行简单策略：监控 {self.trading_pair} 价格...")
        print(f"查询间隔: {self.interval} 秒")

        try:
            while True:
                ticker = self.client.get_ticker(self.trading_pair)
                if ticker:
                    print(
                        f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}, "
                        f"交易对: {self.trading_pair}, "
                        f"最新价: {ticker.last}"
                    )
                else:
                    print(f"未能获取 {self.trading_pair} 的 Ticker 信息。")

                # 等待指定的间隔时间
                time.sleep(self.interval)

        except KeyboardInterrupt:
            print("\n策略执行被用户中断。")
        except Exception as e:
            print(f"策略执行过程中发生错误: {e}")
