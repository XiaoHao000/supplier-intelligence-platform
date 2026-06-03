#!/bin/bash
# ============================================
# 三项目一键部署脚本 — Ubuntu 22.04
# 运行方式: bash deploy_all.sh
# ============================================
set -e

YOUR_API_KEY="sk-你的真实API_KEY"

echo "=== [1/5] 安装 Docker ==="
apt-get update -qq && apt-get install -y -qq docker.io docker-compose-v2 git curl
systemctl enable docker --now
echo "Docker 版本: $(docker --version)"
echo "Compose 版本: $(docker compose version)"

echo ""
echo "=== [2/5] 拉取项目 ==="
cd /opt
git clone https://github.com/XiaoHao000/smart-travel-assistant.git travel || (cd travel && git pull)
git clone https://github.com/XiaoHao000/multi-modal-analysis-system.git multimodal || (cd multimodal && git pull)
git clone https://github.com/XiaoHao000/customer-service-rag-system.git qa-system || (cd qa-system && git pull)

echo ""
echo "=== [3/5] 配置 API Key ==="
for dir in /opt/travel /opt/multimodal /opt/qa-system; do
    # 从模板创建 .env（.env 不会被 git clone 下来，因为 .gitignore）
    if [ ! -f "$dir/.env" ] && [ -f "$dir/.env.example" ]; then
        cp "$dir/.env.example" "$dir/.env"
        echo "  从 .env.example 创建 $dir/.env"
    fi
    if [ -f "$dir/.env" ]; then
        # 替换所有常见的 API Key 占位符
        sed -i "s/API_KEY=.*/API_KEY=$YOUR_API_KEY/" "$dir/.env"
        sed -i "s/sk-xxx/$YOUR_API_KEY/g" "$dir/.env"
        sed -i "s/sk-your-api-key-here/$YOUR_API_KEY/g" "$dir/.env"
        sed -i "s/your_dashscope_api_key_here/$YOUR_API_KEY/g" "$dir/.env"
    fi
    echo "  配置完成: $dir"
done

echo ""
echo "=== [4/5] 启动服务 ==="
cd /opt/travel && docker compose up -d --build
echo "  旅游助手启动中..."

cd /opt/multimodal && docker compose up -d --build
echo "  多模态平台启动中..."

cd /opt/qa-system && docker compose up -d --build
echo "  客服系统启动中..."

echo ""
echo "=== [5/5] 等待服务就绪 ==="
echo "  等待 120 秒让所有服务初始化..."
sleep 120

echo ""
echo "=== 检查服务状态 ==="
echo ""
echo "--- 旅游 (端口 8085) ---"
curl -s http://localhost:8085/health 2>/dev/null || echo "  还在启动中..."
echo ""
echo "--- 多模态 (端口 8000) ---"
curl -s http://localhost:8000/health 2>/dev/null || echo "  还在启动中..."
echo ""
echo "--- 客服 (端口 8087) ---"
curl -s http://localhost:8087/health 2>/dev/null || echo "  还在启动中..."

echo ""
echo "=== Prometheus 指标端点 ==="
echo "  http://36.140.101.127:8085/metrics"
echo "  http://36.140.101.127:8000/metrics"
echo "  http://36.140.101.127:8087/metrics"

echo ""
echo "============================================"
echo "  部署完成!"
echo "  旅游:   http://36.140.101.127:8085"
echo "  多模态: http://36.140.101.127:8000"
echo "  客服:   http://36.140.101.127:8087"
echo "============================================"
