from core.engine import TradingEngine


def main():
    """
    程序主入口。
    初始化并启动交易引擎。
    """
    print("欢迎使用 Gate.io 量化交易程序!")

    # 指定配置文件的路径
    config_file = "config.ini"

    try:
        # 创建交易引擎实例
        engine = TradingEngine(config_path=config_file)

        # 初始化引擎（加载配置、连接API、加载策略）
        engine.initialize()

        # 启动引擎
        engine.run()

    except FileNotFoundError:
        print(f"错误: 配置文件 '{config_file}' 未找到。")
    except Exception as e:
        print(f"程序启动失败: {e}")
        # 可以在这里添加更详细的日志记录
        # import traceback
        # traceback.print_exc()


if __name__ == "__main__":
    main()
