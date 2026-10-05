> ~/opcua-lab/docs/topic-spec.md && cat > ~/opcua-lab/docs/topic-spec.md << 'MDEOF'
# EDGE-IOT-2026 统一命名空间（UNS）主题规范 v1.0

## 1. 设计依据

参考 ISA-95 分层模型，结合现场实际结构（厂区 / 线 / PLC / 变频器）。

| ISA-95 层 | 本项目对应 | 是否进主题 |
|---|---|---|
| Enterprise | 造船厂 | 省略 |
| Site | 厂区（lh / sj） | 是 |
| Area | 线（zone14 / line1） | 是 |
| WorkCenter | PLC（plc1 / plc2） | 是 |
| WorkUnit | 变频器（drive_1 ~ drive_8） | 在 payload 内区分 |

车间信息不进主题，而是作为 InfluxDB 的 tag 存储（见第 8 节）。

## 2. 主题结构

edge-iot/v1/{site}/{line}/{plc}/{type}

| 段 | 含义 | 取值范围 |
|---|---|---|
| edge-iot | 项目前缀（固定） | — |
| v1 | 协议版本（固定） | — |
| {site} | 厂区 | lh / sj |
| {line} | 线号 | zone3~zone14 / line1~line6 |
| {plc} | PLC 编号（线内编号） | plc1 / plc2 |
| {type} | 消息类型 | data / alarms / status / cmd |

## 3. 消息类型

| 类型 | 方向 | QoS | Retain | 说明 |
|---|---|---|---|---|
| data | 上行 | 1 | 否 | 周期采集数据（每 5 秒一帧） |
| alarms | 上行 | 1 | 是 | 报警事件 |
| status | 上行 | 1 | 是 | 网关运行状态 |
| cmd | 下行 | 1 | 否 | 中心下发命令（预留） |

Retain 说明：

- alarms 用 retain，新订阅者一连接就能看到当前还在报警的列表
- status 用 retain，新订阅者立刻知道网关在线状态
- data 不用 retain，周期数据只关心最新

## 4. 系统级主题（独立子树）

| 主题 | QoS | Retain | 说明 |
|---|---|---|---|
| edge-iot/v1/system/health | 0 | 否 | 所有网关健康上报（每 60 秒） |
| edge-iot/v1/system/alerts | 1 | 是 | 系统级告警（网关离线、磁盘满等） |

## 5. 完整主题示例

联合厂区 14 区 PLC1：

edge-iot/v1/lh/zone14/plc1/data
edge-iot/v1/lh/zone14/plc1/alarms
edge-iot/v1/lh/zone14/plc1/status
edge-iot/v1/lh/zone14/plc1/cmd

上建厂区 5 线 PLC2：

edge-iot/v1/sj/line5/plc2/data
edge-iot/v1/sj/line5/plc2/alarms
edge-iot/v1/sj/line5/plc2/status

## 6. 通配符订阅示例

| 场景 | 订阅主题 |
|---|---|
| 全厂所有数据 | edge-iot/v1/+/+/+/data |
| 联合厂区所有数据 | edge-iot/v1/lh/+/+/data |
| 14 区两个 PLC 数据 | edge-iot/v1/lh/zone14/+/data |
| 全厂所有报警 | edge-iot/v1/+/+/+/alarms |
| 全厂所有网关健康 | edge-iot/v1/system/health |

## 7. Payload 格式

### 7.1 data 主题

{
  "timestamp": 1791163000000,
  "plc": "lh_zone14_plc1",
  "values": {
    "drive_1_zsw1": 3855,
    "drive_1_nist_a": 12000,
    "drive_1_iatst_glatt": 8000,
    "drive_1_warn_code": 0,
    "drive_1_fault_code": 0
  }
}

### 7.2 alarms 主题

{
  "timestamp": 1791163000000,
  "plc": "lh_zone14_plc1",
  "drive": "drive_3",
  "kind": "fault",
  "code": 7900,
  "text": "驱动：电机堵转",
  "severity": "critical",
  "category": "fault"
}

### 7.3 status 主题

{
  "timestamp": 1791163000000,
  "plc": "lh_zone14_plc1",
  "state": "online",
  "version": "2.0.0",
  "uptime_s": 86400
}

## 8. 车间信息在 InfluxDB 的存储

车间不进 MQTT 主题，但在 InfluxDB 里作为 tag 保留，方便 Grafana 按车间筛选。

### 8.1 config.yaml 增加字段

plcs:
  - name: "lh_zone14_plc1"
    workshop: "ws1"

### 8.2 InfluxDB 写入时使用

Point("drive_metrics")
    .tag("plc", "lh_zone14_plc1")
    .tag("drive", "drive_1")
    .tag("workshop", "ws1")

### 8.3 Grafana 查询示例

from(bucket: "industrial_data")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "drive_metrics")
  |> filter(fn: (r) => r.workshop == "ws1")

## 9. 迁移方案

| 阶段 | 主题 | 时间 |
|---|---|---|
| 当前 | factory/lh/zone14/plc1/data | 现在 |
| 迁移后 | edge-iot/v1/lh/zone14/plc1/data | Day 21 真机验证时 |

迁移要做的事：

1. config.yaml：所有 topic 字段从 factory/... 改成 edge-iot/v1/...
2. emqx_conf/acl.conf：ACL 规则同步更新
3. Grafana 看板：订阅主题过滤条件更新
4. config.example.yaml：模板同步更新

为什么推到 Day 21：改主题会牵动配置、代码、ACL、Grafana 四处，集中改一次比分散改更高效。

## 10. 版本演进规则

- v1 保持不变，直到有破坏性变更
- 未来可能的 v2：加设备级主题、加命令回执主题
- 不改 v1 现有语义：老订阅者永远能继续工作

## 11. 与 Sparkplug B 的对比

不采用 Sparkplug B 的原因：

| Sparkplug B 要求 | 本项目情况 |
|---|---|
| 每个设备一个 MQTT 客户端 | 网关代理多设备，不匹配 |
| 强制 Protobuf 编码 | 用 JSON，可读性更好 |
| 强制 BIRTH/DEATH 生命周期 | 用 status 主题简化处理 |
| 学习曲线陡 | 团队小，成本高 |

ISA-95 分层 + 自定义 JSON payload 更适合当前阶段。

## 12. 命名约束

| 段 | 规则 |
|---|---|
| {site} | 小写字母，无特殊符号 |
| {line} | zone 或 line 前缀 + 数字（如 zone14、line1） |
| {plc} | plc + 数字（如 plc1、plc2） |
| {type} | 小写，取值枚举：data / alarms / status / cmd |

约定：

- 主题层级用 / 分隔
- 不使用空格、中文、特殊字符
- 主题不区分大小写，统一用小写
