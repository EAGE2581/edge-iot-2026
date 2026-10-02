#!/bin/bash
# 安装 collector 为 systemd 服务
# 用法：sudo bash deploy/install.sh
set -e

SERVICE=collector
SRC="$(cd "$(dirname "$0")" && pwd)/${SERVICE}.service"
DST="/etc/systemd/system/${SERVICE}.service"

if [ "$EUID" -ne 0 ]; then
    echo "请用 sudo 运行：sudo bash $0"
    exit 1
fi

if [ ! -f "$SRC" ]; then
    echo "找不到 $SRC"
    exit 1
fi

echo "[1/4] 复制 service 文件到 $DST"
cp "$SRC" "$DST"

echo "[2/4] 重新加载 systemd"
systemctl daemon-reload

echo "[3/4] 启用开机自启"
systemctl enable "$SERVICE"

echo "[4/4] 启动服务"
systemctl restart "$SERVICE"

echo
echo "完成。常用命令："
echo "  sudo systemctl status $SERVICE     # 看状态"
echo "  sudo journalctl -u $SERVICE -f     # 实时看日志"
echo "  sudo systemctl stop $SERVICE       # 停止"
echo "  sudo systemctl restart $SERVICE    # 重启"
