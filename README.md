# EDGE-IOT-2026

> 工业物联网边缘数据采集系统 — 从西门子 S7-1200 采集 G120C 变频器数据，实现实时监控、报警翻译、断网缓存与钉钉推送。

## 简介

面向造船厂产线设备的边缘采集系统。通过 OPC UA 读取 S7-1200 PLC 下的 G120C 变频器数据，在边缘侧完成换算、清洗、报警翻译，通过 MQTT over TLS 上行，最终写入 InfluxDB 供 Grafana 可视化。

## 功能特性

- OPC UA 订阅 + 轮询混合采集：快变数据用订阅，缓变量用轮询
- 数据换算：归一化整数 → 真实电流 / 转速 / 温度
- 数据清洗：脏数据（超量程、通信中断标志）不入库
- 报警翻译：G120C 报警代码 → 中文（303 条字典，从博途 XML 自动生成）
- 报警去重：同一设备同一代码 5 分钟窗口内只发一次
- 钉钉推送：critical 级报警实时推送到群
- 断网缓存：SQLite 缓存，恢复后自动补发
- 降采样：每 5 分钟聚合均值，原始 30 天 / 降采样 1 年
- 健康上报：每分钟上报 CPU / 内存 / 缓存积压到 MQTT
- systemd 托管：进程崩溃自动重启
- TLS 双向认证：MQTT over TLS 1.3 + mTLS
- ACL 权限矩阵：客户端证书 CN → 白名单主题

## 架构

    ┌──────────────────────────────────────────┐
    │  PLC 层（西门子 S7-1200 + G120C）         │
    └──────────────────────────────────────────┘
                       │ OPC UA (ns=4)
                       ↓
    ┌──────────────────────────────────────────┐
    │  边缘采集层（Python）                     │
    │  config_loader / node_builder            │
    │  subscriber / converter / alarm_codes    │
    │  cache / transports / notifier / health  │
    │  downsampler / worker                    │
    └──────────────────────────────────────────┘
                       │ MQTT over TLS 1.3 + mTLS
                       ↓
    ┌──────────────────────────────────────────┐
    │  EMQX 5.8（Docker）                       │
    │  TLS 8883（双向认证）+ ACL 白名单         │
    └──────────────────────────────────────────┘
                       │
            ┌──────────┼──────────┐
            ↓          ↓          ↓
       InfluxDB    Grafana    钉钉机器人

## 技术栈

| 层 | 技术 |
|---|---|
| 采集 | Python 3.12、asyncua |
| 消息 | MQTT（paho-mqtt）、EMQX 5.8 |
| 存储 | InfluxDB 2.7、SQLite |
| 可视化 | Grafana 11 |
| 部署 | Docker、systemd |
| 安全 | TLS 1.3、mTLS、ACL |
| 测试 | pytest、pytest-cov |
| 告警 | 钉钉 Webhook |

## 快速开始

### 前置

- WSL2 Ubuntu 24.04
- Docker Desktop（EMQX / InfluxDB / Grafana）
- Python 3.12+
- 西门子 S7-1200 PLC（已开启 OPC UA Server）

### 安装

    git clone https://github.com/YOUR_USERNAME/edge-iot-2026.git
    cd edge-iot-2026
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

### 配置

    cp config.example.yaml config.yaml
    # 编辑 config.yaml：填入 MQTT host/port、InfluxDB token、钉钉 webhook

### 生成证书

    cd certs
    openssl genrsa -out ca.key 4096
    openssl req -x509 -new -key ca.key -out ca.crt -days 3650 \
      -subj "/C=CN/O=EDGE-IOT-2026/CN=edge-iot-ca" \
      -addext "keyUsage=critical,keyCertSign,cRLSign"

服务端和客户端证书详见 docs/。

### 运行

    # 全部 PLC
    python3 collector.py config.yaml

    # 单个 PLC
    python3 collector.py config.yaml --plc lh_zone14_plc1

### systemd 部署

    sudo bash deploy/install.sh
    sudo systemctl status collector
    sudo journalctl -u collector -f

## 项目结构

    edge-iot-2026/
    ├── collector.py
    ├── config.yaml               配置（不进 git）
    ├── config.example.yaml       脱敏模板
    ├── alarm_codes.yaml          报警字典（303 条）
    ├── requirements.txt
    ├── pytest.ini
    ├── Dockerfile
    ├── .dockerignore
    ├── app/
    │   ├── config_loader.py
    │   ├── node_builder.py
    │   ├── subscriber.py         OPC UA 订阅管理
    │   ├── converter.py
    │   ├── alarm_codes.py
    │   ├── cache.py
    │   ├── transports.py
    │   ├── notifier.py
    │   ├── health.py
    │   ├── downsampler.py
    │   └── worker.py
    ├── tests/
    ├── tools/
    │   ├── xml2yaml.py
    │   ├── test_tls.py
    │   └── test_subscribe.py
    ├── deploy/
    │   ├── collector.service
    │   └── install.sh
    ├── docs/
    │   └── topic-spec.md
    └── certs/                    证书（不进 git）

## 技术决策

### 采集模式：OPC UA 订阅 + 轮询混合

不同字段的时序特性差异很大，用单一模式都不合适：

| 字段类型 | 示例 | 变化特性 | 采用方式 |
|---|---|---|---|
| 快变模拟量 | 电流、转速、扭矩 | 启停时几百毫秒内冲 2~3 倍额定 | OPC UA 订阅 |
| 事件型 | 状态字、报警码、故障码 | 不变则已，变则瞬间 | OPC UA 订阅 |
| 缓变量 | 温度、直流母线电压、输出电压 | 分钟级热惯性 | OPC UA 轮询 |

为什么不用纯轮询：5 秒轮询会漏掉启动瞬态。变频器启动瞬间电流冲到 2~3 倍额定，几百毫秒后回落——这是过流保护、堵转检测、启动失败诊断的最有价值数据，丢不得。

为什么不用纯订阅：温度这类缓变量 5 分钟才变一次，订阅纯属浪费 PLC 和网关资源。几十个点位全部订阅，回调开销也大。

### 订阅数据的写入策略

订阅回调在数据频繁变化时可能每秒钟被触发几十次。如果每次回调都写 InfluxDB，会同时造成两个问题：

1. 回调被 I/O 阻塞，订阅缓冲区溢出丢数据
2. 30 天数据量爆炸（估算约 74 亿点）

采用方案：

- 回调只更新内存（最新值字典），耗时 < 1ms
- 主循环每 5 秒取一次快照，合并轮询数据后一起写入 InfluxDB

为什么不采用"边缘峰值记录"：数据进库后，Grafana 可以自己算 max_over_time / mean，不需要在边缘侧再算一遍。

### 为什么不用 Sparkplug B

Sparkplug B 要求每个设备一个 MQTT 客户端、强制 Protobuf 编码、强制 BIRTH/DEATH 生命周期。本项目是"网关代理多设备"模式，不适配。改用 ISA-95 分层 + 自定义 JSON payload。

## 主题规范

    edge-iot/v1/{site}/{line}/{plc}/{type}

    type = data / alarms / status / cmd

    # 例
    edge-iot/v1/lh/zone14/plc1/data
    edge-iot/v1/sj/line5/plc2/alarms

设计依据：ISA-95 分层模型。Site = 厂区，Area = 线，WorkCenter = PLC，WorkUnit（变频器）在 payload 内区分。

详见 docs/topic-spec.md。

## 安全设计

- PLC 侧零改动：现场规则不允许修改 PLC 网络配置，所有安全防御在网关和 EMQX 侧做
- mTLS 双向认证：客户端证书 CN → EMQX 用户名 → ACL 规则
- 白名单模式：no_match = deny，默认拒绝，只放行必要操作
- 主题级权限：edge-gateway 只能发 edge-iot/v1/+/+/+/data|alarms|status

## 测试

    pytest --cov=app --cov-report=term-missing

核心模块（converter / node_builder / alarm_codes / cache）覆盖率 76% ~ 100%。

## 开发进度

- [x] Day 1~7：核心采集 + 报警 + 缓存 + 推送
- [x] Day 8~10：TLS 单向 + 双向认证
- [x] Day 11：ACL 权限矩阵
- [x] Day 13：UNS 主题规范
- [x] Day 16：Docker 多阶段构建
- [x] Day 17：pytest 单元测试
- [x] Day 18：订阅 + 轮询混合采集模式 + README
- [ ] Day 19：GitHub Actions CI
- [ ] Day 20：Prometheus 监控
- [ ] Day 21：Loki 日志
- [ ] 真机验证

## 作者

hldqa · 电气工程师 → IT/OT 融合方向

## License

MIT
