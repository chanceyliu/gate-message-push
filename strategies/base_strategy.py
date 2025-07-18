from abc import ABC, abstractmethod
from gateclient.client import GateIOClient


class BaseStrategy(ABC):
    """
    所有策略的基类，定义了策略必须实现的通用接口。
    """

    def __init__(self, client, config: dict = None):
        """
        初始化策略。
        :param client: GateIOClient 实例，用于与 API 交互。在回测中可以为 None。
        :param config: 策略的特定配置字典。
        """
        self.client = client
        self.config = config or {}
        self.trading_pair = self.config.get("trading_pair", "BTC_USDT")
        # 从交易对中解析出基础货币和计价货币
        self.base_currency, self.quote_currency = self.trading_pair.split("_")
        self.engine = None

    def set_engine(self, engine):
        """
        将策略与引擎关联。
        """
        self.engine = engine

    @abstractmethod
    def run(self):
        """
        实盘交易的主逻辑。
        """
        pass

    def on_kline(self, klines_df):
        """
        回测时由引擎调用的方法，每根K线都会调用一次。
        默认实现为空，子类可以覆盖它。
        """
        pass
