# 量化交易程序服务器部署手册

本文档详细记录了将本项目部署到 Linux (以 CentOS 为例) 服务器，并使用 `systemd` 实现持久化、自动化运行的完整步骤和常见问题解决方案。

---

## 目录

1.  [环境准备](#1-环境准备)
2.  [项目配置](#2-项目配置)
3.  [依赖安装与故障排查](#3-依赖安装与故障排查)
4.  [手动运行测试](#4-手动运行测试)
5.  [配置 systemd 服务](#5-配置-systemd-服务)
6.  [管理后台服务](#6-管理后台服务)
7.  [更新代码后的重新部署流程](#7-更新代码后的重新部署流程)

---

### 1. 环境准备

确保您的服务器已安装必要的软件。

```bash
# 更新软件包列表
sudo yum update -y

# 安装 Python 3, pip, venv 和 git
sudo yum install -y python3 python3-pip git
```

通过 `git` 克隆项目代码到服务器。

```bash
# 替换为您的代码仓库地址
git clone <your_repository_url>

# 进入项目目录
cd lianghua
```

为项目创建并激活 Python 虚拟环境。

```bash
# 创建名为 venv 的虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate
```

> **提示**: 激活虚拟环境后，您的终端提示符前会出现 `(venv)` 标识。后续所有 `pip` 和 `python` 命令都将在此独立环境中执行。

### 2. 项目配置

项目依赖两个配置文件。

- **`gate_config.env`**: 存储敏感的 API Key。
- **`config.ini`**: 存储交易对、策略参数等。

首先，创建并编辑 API Key 配置文件。

```bash
# 从模板复制配置文件
cp gate_config.env.example gate_config.env

# 使用 nano 或 vim 编辑器填入您的真实 Key 和 Secret
nano gate_config.env
```

> **安全警告**: 确保 `gate_config.env` 文件已被添加到 `.gitignore` 中，防止被意外提交到代码仓库。

然后，检查 `config.ini` 文件，确保其中的交易对、策略参数符合您的部署预期。

### 3. 依赖安装与故障排查

在虚拟环境中，使用 `requirements.txt` 安装所有依赖。

```bash
pip install -r requirements.txt
```

**常见故障排查**:
在老的 Linux 发行版 (如 CentOS 7) 上，可能会因为系统底层库版本过旧而导致安装失败。我们在部署过程中遇到了以下两个问题：

1.  **问题一: `urllib3` 与 `OpenSSL` 版本不兼容**

    - **报错信息**: `ImportError: urllib3 v2 only supports OpenSSL 1.1.1+...`
    - **原因**: 服务器的 OpenSSL 版本过低，无法支持最新版的 `urllib3` 库。
    - **解决方案**: 在 `requirements.txt` 中添加一行，限制 `urllib3` 的版本。
      ```txt
      # requirements.txt
      urllib3<2.0
      ```

2.  **问题二: `numpy` 新版本移除 `NaN` 别名**
    - **报错信息**: `cannot import name 'NaN' from 'numpy'`
    - **原因**: 项目依赖的 `pandas-ta` 库使用了 `numpy.NaN` 写法，但在 `numpy 1.24` 以上版本中该别名已被移除。
    - **解决方案**: 在 `requirements.txt` 中添加一行，限制 `numpy` 的版本。
      ```txt
      # requirements.txt
      numpy<1.24
      ```

**在修改完 `requirements.txt` 后，请务必执行以下命令强制重新安装所有依赖，以确保版本限制生效。**

```bash
pip install -r requirements.txt --force-reinstall
```

### 4. 手动运行测试

在配置后台服务之前，务必在前台手动运行一次主程序，以确保代码和环境都没有问题。

```bash
# 确保您在虚拟环境中
python main.py
```

> **目的**: 如果程序能正常启动并打印监控日志，说明准备工作全部完成。如果报错，可以直观地看到错误信息，方便排查。只有这一步成功后，才能继续配置后台服务。

### 5. 配置 systemd 服务

`systemd` 是现代 Linux 系统中管理后台服务的标准工具，它可以实现程序崩溃后自动重启和开机自启。

**第一步: 创建服务文件**

```bash
sudo nano /etc/systemd/system/lianghua.service
```

**第二步: 填入服务配置**
将以下内容复制到编辑器中。**注意：请根据您的实际情况修改 `User` 和项目路径！**

```ini
[Unit]
# 服务的描述信息
Description=Gate.io Quantitative Trading Bot for lianghua project
# 表示服务在网络连接准备好之后再启动
After=network.target

[Service]
# 运行服务的用户名 (如果是 root 用户，请填写 root)
User=root
# 项目的绝对路径
WorkingDirectory=/root/project/lianghua
# 要执行的启动命令 (必须是绝对路径)
ExecStart=/root/project/lianghua/venv/bin/python main.py

# 设置服务在失败时自动重启
Restart=on-failure
# 两次重启之间的间隔时间
RestartSec=5s

# 将日志输出到 systemd 的日志系统 (journald)
StandardOutput=journal
StandardError=journal

[Install]
# 定义服务在哪个运行级别下被启用 (多用户模式)
WantedBy=multi-user.target
```

**第三步: 保存并退出**

- `Ctrl + X`, 然后按 `Y`, 最后按 `Enter`。

### 6. 管理后台服务

创建好服务文件后，使用 `systemctl` 命令来管理您的服务。

- **重新加载配置**: 让 systemd 读取到新的服务文件。
  ```bash
  sudo systemctl daemon-reload
  ```
- **启动服务**:
  ```bash
  sudo systemctl start lianghua.service
  ```
- **设置开机自启**:
  ```bash
  sudo systemctl enable lianghua.service
  ```
- **查看服务状态 (非常重要！)**:

  ```bash
  sudo systemctl status lianghua.service
  ```

  > 检查 `Active:` 行是否显示为 `active (running)`。

- **实时查看日志**:
  ```bash
  journalctl -u lianghua.service -f
  ```
- **停止服务**:
  ```bash
  sudo systemctl stop lianghua.service
  ```
- **重启服务**:
  ```bash
  sudo systemctl restart lianghua.service
  ```

### 7. 更新代码后的重新部署流程

当您修改了策略或代码后，标准的更新流程如下：

1.  **在本地提交代码** 到 Git 仓库。
2.  **SSH 登录服务器**，进入项目目录。
3.  **拉取最新代码**: `git pull`
4.  **(如果需要) 更新依赖**: 如果您修改了 `requirements.txt`，请执行 `source venv/bin/activate` 和 `pip install -r requirements.txt`。
5.  **重启服务**: `sudo systemctl restart lianghua.service`
6.  **检查状态和日志**: `sudo systemctl status lianghua.service` 和 `journalctl -u lianghua.service -f` 确保新版代码正常运行。
