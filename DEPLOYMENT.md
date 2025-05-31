# Suna 开源版本部署指南

本文档详细介绍如何在不同环境中部署 Suna 开源版本。

## 📋 目录

- [系统要求](#系统要求)
- [快速部署](#快速部署)
- [详细部署步骤](#详细部署步骤)
- [生产环境部署](#生产环境部署)
- [Docker 部署](#docker-部署)
- [Kubernetes 部署](#kubernetes-部署)
- [故障排除](#故障排除)
- [性能优化](#性能优化)
- [安全配置](#安全配置)
- [监控和日志](#监控和日志)

## 🖥️ 系统要求

### 最低配置

- **CPU**: 2核心
- **内存**: 4GB RAM
- **存储**: 20GB 可用空间
- **网络**: 稳定的网络连接

### 推荐配置

- **CPU**: 4核心或更多
- **内存**: 8GB RAM 或更多
- **存储**: 50GB SSD
- **网络**: 千兆网络

### 软件要求

- **操作系统**: 
  - Ubuntu 20.04+ / CentOS 8+ / RHEL 8+
  - macOS 11+
  - Windows 10+ (with WSL2)
- **Docker**: 20.10+
- **Docker Compose**: 2.0+
- **Python**: 3.9+
- **Node.js**: 16+ (可选，用于前端开发)
- **Git**: 2.0+

## 🚀 快速部署

### 一键部署脚本

**Linux/macOS:**
```bash
# 克隆项目
git clone <repository-url>
cd suna

# 运行一键部署
./start.sh
```

**Windows:**
```cmd
# 克隆项目
git clone <repository-url>
cd suna

# 运行一键部署
start.bat
```

### 使用 Python 脚本

```bash
# 安装依赖
pip install -r scripts/requirements.txt

# 启动所有服务
python scripts/start-opensource.py start

# 查看服务状态
python scripts/start-opensource.py status

# 健康检查
python scripts/health-check.py check
```

## 📝 详细部署步骤

### 1. 环境准备

#### 安装 Docker

**Ubuntu/Debian:**
```bash
# 更新包索引
sudo apt update

# 安装必要的包
sudo apt install apt-transport-https ca-certificates curl gnupg lsb-release

# 添加 Docker 官方 GPG 密钥
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# 设置稳定版仓库
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 安装 Docker Engine
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 启动 Docker 服务
sudo systemctl start docker
sudo systemctl enable docker

# 将用户添加到 docker 组
sudo usermod -aG docker $USER
```

**CentOS/RHEL:**
```bash
# 安装必要的包
sudo yum install -y yum-utils

# 设置仓库
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# 安装 Docker Engine
sudo yum install docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 启动 Docker 服务
sudo systemctl start docker
sudo systemctl enable docker

# 将用户添加到 docker 组
sudo usermod -aG docker $USER
```

**macOS:**
```bash
# 使用 Homebrew 安装
brew install --cask docker

# 或者下载 Docker Desktop
# https://www.docker.com/products/docker-desktop
```

#### 安装 Python 依赖

```bash
# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
venv\Scripts\activate  # Windows

# 安装依赖
pip install -r scripts/requirements.txt
pip install -r backend/requirements.txt
pip install -r services/sandbox_manager/requirements.txt
pip install -r services/crawler/requirements.txt
pip install -r services/realtime/requirements.txt
```

### 2. 配置环境变量

```bash
# 复制环境变量模板
cp .env.opensource .env

# 编辑配置文件
nano .env
```

**重要配置项:**

```bash
# 数据库配置
POSTGRES_PASSWORD=your_secure_password

# JWT 密钥（生产环境必须修改）
GOTRUE_JWT_SECRET=your_jwt_secret_key_change_in_production

# MinIO 配置
MINIO_ROOT_USER=your_minio_user
MINIO_ROOT_PASSWORD=your_secure_minio_password

# Redis 密码
REDIS_PASSWORD=your_redis_password

# 应用域名（生产环境）
APP_DOMAIN=your-domain.com
```

### 3. 启动服务

#### 方式一：使用启动脚本

```bash
python scripts/start-opensource.py start
```

#### 方式二：手动启动

```bash
# 启动基础设施服务
docker-compose -f docker-compose.opensource.yml --env-file .env up -d postgres redis rabbitmq minio

# 等待服务就绪
sleep 30

# 启动应用服务
docker-compose -f docker-compose.opensource.yml --env-file .env up -d

# 启动自定义服务
cd services/sandbox_manager && python main.py &
cd services/crawler && python main.py &
cd services/realtime && python main.py &

# 启动后端服务
cd backend && uvicorn main:app --host 0.0.0.0 --port 8000 &
cd backend && celery worker -A worker.celery_app --loglevel=info &
```

### 4. 验证部署

```bash
# 健康检查
python scripts/health-check.py check

# 查看服务状态
python scripts/start-opensource.py status

# 查看日志
docker-compose -f docker-compose.opensource.yml logs -f
```

## 🏭 生产环境部署

### 1. 安全配置

#### 修改默认密码

```bash
# 生成强密码
openssl rand -base64 32

# 更新 .env 文件中的所有密码
```

#### 配置 HTTPS

**使用 Nginx 反向代理:**

```nginx
# /etc/nginx/sites-available/suna
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /path/to/your/certificate.crt;
    ssl_certificate_key /path/to/your/private.key;
    
    # SSL 配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    
    # 前端
    location / {
        proxy_pass http://localhost:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # API
    location /api/ {
        proxy_pass http://localhost:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # WebSocket
    location /ws/ {
        proxy_pass http://localhost:8003/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### 防火墙配置

```bash
# Ubuntu/Debian (ufw)
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable

# CentOS/RHEL (firewalld)
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

### 2. 数据备份

#### 自动备份脚本

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backups/suna"
DATE=$(date +%Y%m%d_%H%M%S)

# 创建备份目录
mkdir -p $BACKUP_DIR

# 备份数据库
docker-compose -f docker-compose.opensource.yml exec -T postgres pg_dump -U suna_app suna_db > $BACKUP_DIR/database_$DATE.sql

# 备份 MinIO 数据
docker-compose -f docker-compose.opensource.yml exec -T minio mc mirror /data $BACKUP_DIR/minio_$DATE

# 压缩备份
tar -czf $BACKUP_DIR/suna_backup_$DATE.tar.gz $BACKUP_DIR/database_$DATE.sql $BACKUP_DIR/minio_$DATE

# 清理旧备份（保留30天）
find $BACKUP_DIR -name "suna_backup_*.tar.gz" -mtime +30 -delete

echo "备份完成: $BACKUP_DIR/suna_backup_$DATE.tar.gz"
```

#### 设置定时备份

```bash
# 添加到 crontab
crontab -e

# 每天凌晨2点备份
0 2 * * * /path/to/backup.sh
```

### 3. 监控配置

#### Prometheus 配置

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'suna-api'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    
  - job_name: 'suna-services'
    static_configs:
      - targets: 
        - 'localhost:8001'  # sandbox_manager
        - 'localhost:8002'  # crawler
        - 'localhost:8003'  # realtime
    metrics_path: '/metrics'
    
  - job_name: 'postgres'
    static_configs:
      - targets: ['localhost:9187']
      
  - job_name: 'redis'
    static_configs:
      - targets: ['localhost:9121']
```

#### 告警规则

```yaml
# alerts.yml
groups:
  - name: suna_alerts
    rules:
      - alert: ServiceDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.instance }} is down"
          
      - alert: HighMemoryUsage
        expr: (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes > 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage on {{ $labels.instance }}"
          
      - alert: HighCPUUsage
        expr: 100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High CPU usage on {{ $labels.instance }}"
```

## 🐳 Docker 部署

### 单机 Docker 部署

```bash
# 使用 Docker Compose
docker-compose -f docker-compose.opensource.yml up -d

# 查看服务状态
docker-compose -f docker-compose.opensource.yml ps

# 查看日志
docker-compose -f docker-compose.opensource.yml logs -f

# 停止服务
docker-compose -f docker-compose.opensource.yml down
```

### Docker Swarm 部署

```bash
# 初始化 Swarm
docker swarm init

# 部署服务栈
docker stack deploy -c docker-compose.opensource.yml suna

# 查看服务状态
docker service ls

# 扩展服务
docker service scale suna_api=3

# 更新服务
docker service update --image suna/api:latest suna_api
```

## ☸️ Kubernetes 部署

### 创建 Kubernetes 配置

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: suna
---
# k8s/postgres.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: suna
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15
        env:
        - name: POSTGRES_DB
          value: "suna_db"
        - name: POSTGRES_USER
          value: "suna_app"
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: password
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
        - name: init-script
          mountPath: /docker-entrypoint-initdb.d
      volumes:
      - name: postgres-storage
        persistentVolumeClaim:
          claimName: postgres-pvc
      - name: init-script
        configMap:
          name: postgres-init
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: suna
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
```

### 部署到 Kubernetes

```bash
# 创建命名空间
kubectl apply -f k8s/namespace.yaml

# 创建密钥
kubectl create secret generic postgres-secret \
  --from-literal=password=your_secure_password \
  -n suna

# 创建配置映射
kubectl create configmap postgres-init \
  --from-file=init.sql=database/init.sql \
  -n suna

# 部署所有服务
kubectl apply -f k8s/

# 查看部署状态
kubectl get pods -n suna
kubectl get services -n suna

# 查看日志
kubectl logs -f deployment/postgres -n suna
```

## 🔧 故障排除

### 常见问题

#### 1. Docker 启动失败

```bash
# 检查 Docker 状态
sudo systemctl status docker

# 重启 Docker 服务
sudo systemctl restart docker

# 检查 Docker 版本
docker --version
docker-compose --version
```

#### 2. 端口冲突

```bash
# 检查端口占用
netstat -tulpn | grep :8000
lsof -i :8000

# 修改端口配置
nano .env
# 或
nano docker-compose.opensource.yml
```

#### 3. 数据库连接失败

```bash
# 检查数据库容器状态
docker-compose -f docker-compose.opensource.yml ps postgres

# 查看数据库日志
docker-compose -f docker-compose.opensource.yml logs postgres

# 测试数据库连接
docker-compose -f docker-compose.opensource.yml exec postgres psql -U suna_app -d suna_db -c "SELECT 1;"
```

#### 4. 内存不足

```bash
# 检查内存使用
free -h
docker stats

# 清理 Docker 资源
docker system prune -a
docker volume prune
```

#### 5. 磁盘空间不足

```bash
# 检查磁盘使用
df -h
du -sh /var/lib/docker

# 清理日志
sudo journalctl --vacuum-time=7d
docker-compose -f docker-compose.opensource.yml logs --tail=0 -f
```

### 调试技巧

#### 查看详细日志

```bash
# 查看所有服务日志
docker-compose -f docker-compose.opensource.yml logs -f

# 查看特定服务日志
docker-compose -f docker-compose.opensource.yml logs -f postgres
docker-compose -f docker-compose.opensource.yml logs -f api

# 查看 Python 服务日志
tail -f services/sandbox_manager/logs/app.log
tail -f services/crawler/logs/app.log
tail -f services/realtime/logs/app.log
```

#### 进入容器调试

```bash
# 进入数据库容器
docker-compose -f docker-compose.opensource.yml exec postgres bash

# 进入 API 容器
docker-compose -f docker-compose.opensource.yml exec api bash

# 执行数据库查询
docker-compose -f docker-compose.opensource.yml exec postgres psql -U suna_app -d suna_db
```

## ⚡ 性能优化

### 数据库优化

```sql
-- 创建索引
CREATE INDEX CONCURRENTLY idx_messages_thread_id ON messages(thread_id);
CREATE INDEX CONCURRENTLY idx_messages_created_at ON messages(created_at);
CREATE INDEX CONCURRENTLY idx_projects_account_id ON projects(account_id);

-- 分析表统计信息
ANALYZE;

-- 查看慢查询
SELECT query, mean_time, calls 
FROM pg_stat_statements 
ORDER BY mean_time DESC 
LIMIT 10;
```

### Redis 优化

```bash
# 配置 Redis
echo "maxmemory 1gb" >> /etc/redis/redis.conf
echo "maxmemory-policy allkeys-lru" >> /etc/redis/redis.conf
echo "save 900 1" >> /etc/redis/redis.conf
echo "save 300 10" >> /etc/redis/redis.conf
echo "save 60 10000" >> /etc/redis/redis.conf
```

### 应用优化

```python
# 连接池配置
DATABASE_POOL_SIZE = 20
DATABASE_MAX_OVERFLOW = 30
REDIS_POOL_SIZE = 50

# 缓存配置
CACHE_TTL = 3600  # 1小时
CACHE_MAX_SIZE = 1000

# 异步处理
WORKER_CONCURRENCY = 4
WORKER_PREFETCH_MULTIPLIER = 1
```

### 系统优化

```bash
# 增加文件描述符限制
echo "* soft nofile 65536" >> /etc/security/limits.conf
echo "* hard nofile 65536" >> /etc/security/limits.conf

# 优化内核参数
echo "net.core.somaxconn = 65535" >> /etc/sysctl.conf
echo "net.ipv4.tcp_max_syn_backlog = 65535" >> /etc/sysctl.conf
echo "vm.swappiness = 10" >> /etc/sysctl.conf
sysctl -p
```

## 📊 监控和日志

### 日志配置

```yaml
# docker-compose.yml 日志配置
services:
  api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### 监控指标

- **系统指标**: CPU、内存、磁盘、网络
- **应用指标**: 请求数、响应时间、错误率
- **数据库指标**: 连接数、查询时间、锁等待
- **缓存指标**: 命中率、内存使用、连接数

### 告警配置

```yaml
# alertmanager.yml
global:
  smtp_smarthost: 'localhost:587'
  smtp_from: 'alerts@your-domain.com'

route:
  group_by: ['alertname']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'web.hook'

receivers:
- name: 'web.hook'
  email_configs:
  - to: 'admin@your-domain.com'
    subject: 'Suna Alert: {{ .GroupLabels.alertname }}'
    body: |
      {{ range .Alerts }}
      Alert: {{ .Annotations.summary }}
      Description: {{ .Annotations.description }}
      {{ end }}
```

---

## 📞 支持

如果在部署过程中遇到问题，请：

1. 查看本文档的[故障排除](#故障排除)部分
2. 检查项目的 [Issues](https://github.com/your-repo/issues)
3. 创建新的 [Issue](https://github.com/your-repo/issues/new)
4. 联系技术支持团队

---

**祝您部署顺利！** 🎉