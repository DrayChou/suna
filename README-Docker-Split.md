# Suna Docker 服务分离部署指南

本项目已将 Docker Compose 配置分离为基础服务和应用服务两部分，以提供更灵活的部署和管理方式。

## 文件结构

- `docker-compose.base.yml` - 基础设施服务配置
- `docker-compose.apps.yml` - 应用服务配置
- `start-suna.ps1` - PowerShell 启动脚本（推荐使用）
- `.env.opensource` - 环境变量配置文件

## 服务分类

### 基础服务 (docker-compose.base.yml)

这些是 Suna 应用依赖的基础设施服务：

- **suna-postgres** - PostgreSQL 数据库 (端口: 5432)
- **suna-postgrest** - PostgREST API 服务 (端口: 3001)
- **suna-gotrue** - GoTrue 认证服务 (端口: 9999)
- **suna-minio** - MinIO 对象存储 (端口: 9000, 9001)
- **suna-redis** - Redis 缓存 (端口: 6379)
- **suna-rabbitmq** - RabbitMQ 消息队列 (端口: 5672, 15672)
- **suna-prometheus** - Prometheus 监控 (端口: 9090)
- **suna-grafana** - Grafana 可视化 (端口: 3002)

### 应用服务 (docker-compose.apps.yml)

这些是 Suna 的核心应用服务：

- **sandbox-manager** - 沙盒管理服务 (端口: 8001)
- **searxng** - 搜索引擎服务 (端口: 8002)
- **suna-crawler** - 爬虫服务 (端口: 8004)
- **realtime-service** - 实时通信服务 (端口: 8003)
- **suna-backend** - 后端 API 服务 (端口: 8000)
- **suna-worker** - 后台工作进程
- **frontend** - 前端服务 (端口: 3000) *当前已注释，因为构建问题*

## 快速启动

### 方法一：使用启动脚本（推荐）

```powershell
# 运行启动脚本
.\start-suna.ps1
```

脚本提供交互式菜单，可以：
- 分别启动基础服务和应用服务
- 一键启动所有服务
- 查看服务状态
- 查看服务日志
- 停止所有服务

### 方法二：手动启动

1. **启动基础服务**
   ```bash
   docker-compose -f docker-compose.base.yml --env-file .env.opensource up -d
   ```

2. **等待基础服务完全启动（约30秒）**

3. **启动应用服务**
   ```bash
   docker-compose -f docker-compose.apps.yml --env-file .env.opensource up -d
   ```

## 服务管理

### 查看服务状态
```bash
docker ps --filter name=suna
```

### 查看服务日志
```bash
# 查看特定服务日志
docker logs -f suna-backend

# 查看所有应用服务日志
docker-compose -f docker-compose.apps.yml logs -f
```

### 停止服务
```bash
# 停止应用服务
docker-compose -f docker-compose.apps.yml down

# 停止基础服务
docker-compose -f docker-compose.base.yml down
```

### 重启特定服务
```bash
# 重启后端服务
docker-compose -f docker-compose.apps.yml restart suna-backend
```

## 访问地址

启动成功后，可以通过以下地址访问各个服务：

- **后端 API**: http://localhost:8000
- **前端界面**: http://localhost:3000 (当前未启用)
- **PostgREST API**: http://localhost:3001
- **GoTrue 认证**: http://localhost:9999
- **MinIO 控制台**: http://localhost:9001
- **RabbitMQ 管理界面**: http://localhost:15672
- **Prometheus 监控**: http://localhost:9090
- **Grafana 仪表板**: http://localhost:3002
- **搜索引擎**: http://localhost:8002
- **实时服务**: ws://localhost:8003

## 故障排除

### 常见问题

1. **网络错误**
   ```bash
   # 创建缺失的网络
   docker network create suna_suna-network
   docker network create suna_suna-sandbox-network
   ```

2. **端口冲突**
   - 检查端口是否被其他服务占用
   - 修改 docker-compose 文件中的端口映射

3. **服务依赖问题**
   - 确保基础服务完全启动后再启动应用服务
   - 检查服务健康状态：`docker ps`

4. **前端构建失败**
   - 当前前端服务已暂时禁用
   - 需要修复前端构建问题后重新启用

### 日志调试

```bash
# 查看启动失败的服务日志
docker-compose -f docker-compose.base.yml logs [service-name]
docker-compose -f docker-compose.apps.yml logs [service-name]

# 实时查看日志
docker logs -f suna-[service-name]
```

## 开发建议

1. **开发环境**：只启动需要的基础服务，本地运行应用服务
2. **测试环境**：启动所有服务进行集成测试
3. **生产环境**：考虑使用 Docker Swarm 或 Kubernetes 进行编排

## 监控和维护

- 使用 Prometheus (http://localhost:9090) 监控服务指标
- 使用 Grafana (http://localhost:3002) 查看可视化仪表板
- 定期检查容器资源使用情况
- 定期备份 PostgreSQL 数据库和 MinIO 存储

## 注意事项

- 确保 Docker 和 Docker Compose 已正确安装
- 首次启动可能需要较长时间下载镜像
- 建议为生产环境配置持久化存储卷
- 定期更新服务镜像版本