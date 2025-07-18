import os
from dotenv import load_dotenv
import gate_api
from gate_api.exceptions import ApiException, GateApiException
import pandas as pd
from datetime import datetime, timedelta
import time


class GateIOClient:
    """
    用于与 Gate.io API 交互的客户端。
    """

    def __init__(self, dotenv_path: str = "gate_config.env"):
        """
        初始化客户端，加载 API 密钥并配置 API 客户端。
        :param dotenv_path: .env 文件的路径。
        """
        # 从指定的 .env 文件加载环境变量
        load_dotenv(dotenv_path=dotenv_path)

        api_key = os.getenv("GATE_API_KEY")
        api_secret = os.getenv("GATE_API_SECRET")

        if not api_key or not api_secret:
            raise ValueError(f"API Key 或 Secret 未在 {dotenv_path} 文件中设置")

        # 配置 API 客户端
        self.configuration = gate_api.Configuration(
            host="https://api.gateio.ws/api/v4", key=api_key, secret=api_secret
        )
        self.api_client = gate_api.ApiClient(self.configuration)
        self.spot_api = gate_api.SpotApi(self.api_client)

    def get_ticker(self, currency_pair: str):
        """
        获取指定交易对的最新 Ticker 信息。

        :param currency_pair: 交易对，例如 "BTC_USDT"
        """
        try:
            # 获取 Ticker 信息
            api_response = self.spot_api.list_tickers(currency_pair=currency_pair)
            if api_response:
                return api_response[0]  # list_tickers 返回的是一个列表
            return None
        except GateApiException as ex:
            print(f"Gate api exception, label: {ex.label}, message: {ex.message}")
            return None
        except ApiException as e:
            print(f"Exception when calling SpotApi->list_tickers: {e}")
            return None

    def get_klines(self, currency_pair: str, interval: str = "4h", limit: int = 100):
        """
        获取指定交易对的 K 线数据。

        :param currency_pair: 交易对, e.g., "BTC_USDT"
        :param interval: K线周期, e.g., '1m', '5m', '1h', '4h', '1d'
        :param limit: 获取的数据条数, 最大 1000
        :return: 包含 K 线数据的 pandas DataFrame，如果失败则返回 None
        """
        try:
            # 获取 K 线数据
            api_response = self.spot_api.list_candlesticks(
                currency_pair=currency_pair, interval=interval, limit=limit
            )
            return self._format_klines_to_dataframe(api_response)

        except GateApiException as ex:
            print(f"Gate api exception, label: {ex.label}, message: {ex.message}")
            return None
        except ApiException as e:
            print(f"Exception when calling SpotApi->list_candlesticks: {e}")
            return None

    def check_currency_pair_exists(self, currency_pair: str) -> bool:
        """
        检查指定的交易对是否存在于交易所。

        :param currency_pair: 交易对, e.g., "BTC_USDT"
        :return: 如果存在则返回 True，否则返回 False。
        """
        try:
            # 尝试获取单个交易对的 ticker 信息
            api_response = self.spot_api.list_tickers(currency_pair=currency_pair)
            # 如果能返回非空结果，说明交易对存在
            return api_response is not None and len(api_response) > 0
        except GateApiException as ex:
            # 捕获特定的API异常，如果错误标签是 INVALID_CURRENCY_PAIR，说明不存在
            if ex.label == "INVALID_CURRENCY_PAIR":
                return False
            # 其他API错误则打印出来，但也认为检查失败
            print(f"Gate api exception while checking pair '{currency_pair}': {ex}")
            return False
        except ApiException as e:
            print(
                f"An unexpected exception occurred while checking pair '{currency_pair}': {e}"
            )
            return False

    def get_historical_klines(
        self,
        currency_pair: str,
        interval: str,
        start_utc: datetime,
        end_utc: datetime,
    ):
        """
        获取指定时间范围内的历史 K 线数据，自动处理分页。

        :param currency_pair: 交易对, e.g., "BTC_USDT"
        :param interval: K线周期, e.g., '1m', '5m', '1h', '4h', '1d'
        :param start_utc: 开始时间 (UTC)
        :param end_utc: 结束时间 (UTC)
        :return: 包含历史 K 线数据的 pandas DataFrame
        """
        print(
            f"开始获取 {currency_pair} 从 {start_utc} 到 {end_utc} 的 {interval} 历史K线数据..."
        )
        all_klines = []
        current_end_ts = int(end_utc.timestamp())
        start_ts = int(start_utc.timestamp())

        while True:
            try:
                # 每次最多获取1000条
                api_response = self.spot_api.list_candlesticks(
                    currency_pair=currency_pair,
                    interval=interval,
                    to=current_end_ts,
                    limit=1000,
                )

                if not api_response:
                    break

                df = self._format_klines_to_dataframe(api_response)
                if df is None or df.empty:
                    break

                all_klines.append(df)

                first_ts_in_response = int(df.index[0].timestamp())

                # 如果获取到的数据已经早于开始时间，或者返回的数据量小于请求量，说明已经获取完所有数据
                if first_ts_in_response <= start_ts or len(df) < 1000:
                    break

                # 更新下一次请求的结束时间戳
                current_end_ts = first_ts_in_response - 1  # 往前推一秒避免重复

                print(f"已获取到 {df.index[0]} 的数据，继续获取更早的数据...")
                # 遵循API频率限制
                time.sleep(0.2)

            except GateApiException as ex:
                print(f"Gate api exception: {ex.label}, {ex.message}")
                break
            except ApiException as e:
                print(f"Exception when calling SpotApi->list_candlesticks: {e}")
                break

        if not all_klines:
            print("未能获取到任何K线数据。")
            return pd.DataFrame()

        # 合并所有获取到的数据
        full_df = pd.concat(all_klines)
        # 删除重复数据并排序
        full_df = full_df[~full_df.index.duplicated(keep="first")]
        full_df.sort_index(ascending=True, inplace=True)

        # 裁剪到请求的精确时间范围
        final_df = full_df[(full_df.index >= start_utc) & (full_df.index <= end_utc)]
        print(
            f"成功获取 {len(final_df)} 条K线数据，时间范围: {final_df.index[0]} 到 {final_df.index[-1]}"
        )
        return final_df

    def _format_klines_to_dataframe(self, klines_data):
        """
        将从 API 获取的 K 线列表格式化为 DataFrame。
        这是一个辅助函数，将 get_klines 中的逻辑提取出来以便复用。
        """
        if not klines_data:
            return None

        columns = [
            "timestamp",
            "quote_volume",
            "close",
            "high",
            "low",
            "open",
            "base_volume",
            "is_finished",
        ]
        df = pd.DataFrame(klines_data, columns=columns)

        df["timestamp"] = pd.to_datetime(df["timestamp"].astype(float), unit="s")

        numeric_columns = [
            "quote_volume",
            "close",
            "high",
            "low",
            "open",
            "base_volume",
        ]
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col])

        df.rename(columns={"base_volume": "volume"}, inplace=True)
        df.set_index("timestamp", inplace=True)
        df.sort_index(ascending=True, inplace=True)

        return df[df["is_finished"] == "true"]

    def get_account_details(self):
        """
        获取现货账户详情，用于测试 API 连接。
        """
        try:
            # 获取现货账户列表
            api_response = self.spot_api.list_spot_accounts()
            return api_response
        except GateApiException as ex:
            print(f"Gate api exception, label: {ex.label}, message: {ex.message}")
            return None
        except ApiException as e:
            print(f"Exception when calling SpotApi->list_spot_accounts: {e}")
            return None


if __name__ == "__main__":
    # 这是一个简单的测试，当你直接运行这个文件时会执行
    # 请确保你已经创建了 gate_config.env 并填入了正确的 API Key
    try:
        client = GateIOClient()
        account_details = client.get_account_details()
        if account_details:
            print("成功获取账户详情:")
            for account in account_details:
                # 只打印非零余额的资产
                if float(account.available) > 0 or float(account.locked) > 0:
                    print(
                        f"  币种: {account.currency}, 可用: {account.available}, 冻结: {account.locked}"
                    )
    except ValueError as e:
        print(e)
