# 第 2 周总结（Day 8~14）

## 完成情况

### Day 8：CA + 服务端证书
- 生成 CA 根证书（10 年有效期）
- 生成 EMQX 服务端证书（2 年有效期）
- 关键点：CA 必须有 keyUsage 扩展，否则 Python 3.14 拒绝验证

### Day 9：MQTT TLS 单向认证
- EMQX 8883 端口启用 TLS
- Python 客户端用 ca.crt 验证服务端
- 验证通过：openssl s_client 和 paho-mqtt 都能连

### Day 10：MQTT TLS 双向认证（mTLS）
- 生成客户端证书（CN=edge-gateway）
- EMQX 配置 verify_peer + fail_if_no_peer_cert
- 验证：不带证书被拒，带证书能连
- 关键点：peer_cert_as_username 在 EMQX 5.8 里属于 mqtt 全局配置，不是 listener 级

### Day 11：MQTT ACL 权限矩阵
- 从客户端证书 CN 提取用户名（peer_cert_as_username=cn）
- 配置白名单规则：edge-gateway 只能发 factory/+/+/+/data|alarms|status
- 默认拒绝：{deny, all}
- 验证：越权发布被 EMQX 断开

### Day 12：扩展到 PLC2（跳过）
- 需真实 PLC 环境，推迟到真机验证

### Day 13：统一命名空间（UNS）主题规范
- 参考 ISA-95 分层
- 新主题结构：edge-iot/v1/{site}/{line}/{plc}/{type}
- 输出：docs/topic-spec.md（189 行）
- 迁移：推迟到真机验证时一起改

### Day 14：第 2 周验收（本文档）

## 验证成果

| 检查项 | 结果 |
|---|---|
| CA 证书自洽 | OK |
| EMQX 服务端证书验证 | Verify return code: 0 (ok) |
| Python 客户端 mTLS 连接 | 成功 |
| 无证书客户端被拒 | is_connected = False |
| 用户名从证书 CN 提取 | username=edge-gateway |
| ACL 白名单生效 | 越权发布被断 |
| UNS 主题规范 | 189 行文档输出 |

## 欠账记录

| 项目 | 原因 | 计划 |
|---|---|---|
| PLC 侧防火墙 | 现场规则不允许动 PLC | 不做 |
| PLC 侧白名单 | 同上 | 不做 |
| 扩展到 PLC2 | 需真实 PLC | 真机验证时做 |
| 主题迁移 | 需同时改代码 + 配置 + ACL + Grafana | 真机验证时集中改 |
| 车间信息（workshop tag） | 需确认现场车间划分 | 待确认后加 |

## 安全架构总结

PLCs（不动）
   |
   | OPC UA 匿名（走 OT 内网）
   v
网关（edge-gateway）
   |
   | MQTT over TLS 1.3 + mTLS
   v
EMQX
   |
   | ACL 白名单
   +-- bridge 订阅 factory/#
   +-- grafana_reader 订阅 factory/+/+/+/data（待建）

## 关键技术决策

1. PLC 侧零改动：现场规则不允许改 PLC 网络配置
2. TLS 单向到双向：先用单向验证链路，再加客户端证书
3. ACL 白名单模式：no_match=deny，只放行必要操作
4. 用户名从证书 CN 提取：不用在 CONNECT 包里传密码
5. 主题规范推迟迁移：避免反复改配置

## 下周计划（Day 15~21）

- Day 15：代码模块化（已完成）
- Day 16：Docker 多阶段构建
- Day 17：pytest 单元测试
- Day 18：GitHub + README
- Day 19：GitHub Actions CI
- Day 20：Prometheus 监控
- Day 21：Loki + Promtail 日志
