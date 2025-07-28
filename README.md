# Gate.io 量化交易程序

本项目是一个使用 Python 语言开发的，针对 Gate.io 交易所的量化交易程序框架。它内置了一个多指标融合的交易策略，并提供了易于扩展的结构，方便开发者实现自己的交易思想。

## 功能特性

- **并发监控**：采用多线程架构，可同时监控多个交易对（如 BTC_USDT, ETH_USDT 等），互不影响。
- **模块化设计**：项目结构清晰，分为核心引擎、策略、API 客户端和工具等模块。
- **配置驱动**：交易对、策略参数等都通过 `config.ini` 文件进行配置，无需修改代码。
- **多指标策略**：内置的 `MovingAverageStrategy` 融合了均线、MACD、RSI 等多个技术指标，并包含止损和移动止盈逻辑。
- **回测支持**：提供了 `backtest.py` 脚本，可以方便地对单一策略进行历史数据回测和评估。
- **扩展性强**：可以方便地在 `strategies` 目录下添加新的策略文件，并通过 `config.ini` 进行切换。
- **微信通知**：可在产生买卖信号时，通过 [PushPlus](http://www.pushplus.plus/) 发送微信通知，方便及时掌握交易动态。

## 项目结构

```
lianghua/
├── core/                       # 核心交易逻辑
│   ├── engine.py               # 实时交易引擎
│   └── backtest_engine.py      # 回测引擎
├── gateclient/                 # 封装 Gate.io API 相关调用
│   └── client.py               # API 客户端
├── notifications/              # 消息通知模块
│   └── pushplus_client.py      # PushPlus 推送客户端
├── strategies/                 # 存放各种交易策略
│   ├── base_strategy.py        # 策略基类
│   └── moving_average_strategy.py # 内置的多指标融合策略
├── utils/                      # 工具类函数
│   └── logger.py               # 日志配置
├── data/                       # 存放数据，例如K线、日志等 (此目录被 git 忽略)
├── tests/                      # 测试用例
│   └── test_api.py
├── .gitignore                  # Git 忽略文件
├── config.ini                  # 项目主配置文件
├── gate_config.env             # API Key 配置文件 (需手动创建)
├── gate_config.env.example     # API Key 配置文件示例
├── main.py                     # 实时交易程序主入口
├── backtest.py                 # 策略回测程序主入口
├── requirements.txt            # Python 依赖包
└── README.md                   # 项目说明
```

## 快速开始

### 1. 环境准备

建议使用 Python 3.8 或更高版本。推荐创建虚拟环境来管理项目依赖。

```bash
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
```

### 2. 安装依赖

从 `requirements.txt` 文件安装所有必要的库。

```bash
pip install -r requirements.txt
```

### 3. 配置 API Key

本项目使用 `gate_config.env` 文件来管理敏感的 API Key 信息。

首先，复制配置文件模板：

```bash
cp gate_config.env.example gate_config.env
```

然后，编辑新创建的 `gate_config.env` 文件，填入你从 Gate.io 申请的真实 API Key 和 Secret。**请注意，如果是用于实盘交易，请务必确保 API Key 的安全！**

```dotenv
# gate_config.env

GATE_API_KEY="YOUR_API_KEY"
GATE_API_SECRET="YOUR_API_SECRET"
```

在 `config.ini` 文件中，你可以配置希望同时监控的交易对：

```ini
[GateIO]
# 要同时监控的交易对列表，用逗号分隔
currency_pairs = BTC_USDT,ETH_USDT,SOL_USDT
```

### 4. 配置微信通知 (可选)

如果你希望在策略产生买入信号时收到微信通知，可以配置 PushPlus 服务。

首先，访问 [PushPlus 官网](http://www.pushplus.plus/)，使用微信扫码登录，然后在“一对一推送”页面找到并复制你的 `token`。

接着，编辑 `gate_config.env` 文件，在末尾添加你的 PushPlus token：

```dotenv
# gate_config.env

GATE_API_KEY="YOUR_API_KEY"
GATE_API_SECRET="YOUR_API_SECRET"

# PushPlus Token for Wechat notification
# Get it from http://www.pushplus.plus/
PUSHPLUS_TOKEN="YOUR_PUSHPLUS_TOKEN"
```

程序会自动读取此配置。如果你不配置 `PUSHPLUS_TOKEN`，程序会跳过通知功能，正常运行。

你还可以在 `config.ini` 的 `[PushPlus]` 段落中，通过 `backtest_notify_enabled` 参数来控制在**回测时**是否发送通知，以及是否只发送一次。

- `backtest_notify_enabled = true`: 回测时，仅在遇到第一个买入或卖出信号时发送**一条**通知，然后在本轮回测中不再发送。
- `backtest_notify_enabled = false`: 回测时，完全关闭通知功能。

实时交易模式不受此参数影响，会始终发送所有信号通知。

### 5. 运行实时交易

通过 `main.py` 脚本启动实时交易程序。程序会根据 `config.ini` 的配置，为每个交易对启动一个独立的监控线程。

```bash
python main.py
```

程序启动后，你会在控制台看到实时日志输出，显示每个交易对的当前价格、指标状态以及产生的交易信号。

### 6. 运行策略回测

在开发和调整策略时，使用历史数据进行回测是至关重要的一步。项目提供了 `backtest.py` 脚本来支持此功能。

回测前，请确保 `config.ini` 中的 `[Backtest]` 部分已正确配置。你需要指定用于回测的单个交易对、K 线周期以及策略名称。

运行以下命令启动回测：

```bash
python backtest.py
```

回测结束后，程序会输出一份包含各项性能指标的报告，例如总回报率、夏普比率、最大回撤等。同时，可能会生成一张带有交易信号标记的 K 线图，保存在 `data` 目录下，方便你直观地评估策略表现。

## 策略开发

要实现你自己的交易策略，可以遵循以下步骤：

1.  在 `strategies` 目录下，创建一个新的 Python 文件，例如 `my_strategy.py`。
2.  在该文件中，创建一个继承自 `BaseStrategy` 的类。`BaseStrategy` 定义在 `strategies/base_strategy.py` 中。
3.  实现 `generate_signals` 方法。该方法接收 K 线数据 (Pandas DataFrame) 作为输入，并应返回交易信号（`'buy'`, `'sell'`, `'wait'`）。
4.  在 `config.ini` 文件中，将 `strategy_name` 参数修改为你的新策略类名，然后运行回测或实时交易来测试它。

可以参考 `strategies/moving_average_strategy.py` 作为实现示例。

## 风险提示

本项目仅为量化交易学习和研究目的，不构成任何投资建议。

数字货币市场波动剧烈，风险极高。在进行实盘交易前，请务必充分理解项目代码、自行进行详尽的回测和风险评估，并由使用者自行承担所有风险。**开发者对任何使用本项目代码造成的资产损失不负任何责任。**
