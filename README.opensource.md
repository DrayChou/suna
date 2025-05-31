# Suna 开源版本

这是 Suna 项目的完全开源替代方案，使用开源组件替代所有商业服务，实现完全离线运行。

## 🎯 项目目标

- **完全开源**: 使用开源组件替代所有商业服务
- **离线运行**: 支持完全离线环境运行
- **功能完整**: 保持与原版相同的核心功能
- **易于部署**: 一键启动所有服务

## 🏗️ 架构概览

### 服务替代方案

| 原商业服务 | 开源替代 | 说明 |
|-----------|----------|------|
| Supabase Database | PostgreSQL + PostgREST | 数据库和REST API |
| Supabase Auth | GoTrue | 用户认证和授权 |
| Supabase Storage | MinIO | 对象存储服务 |
| Supabase Realtime | 自定义WebSocket服务 | 实时通信 |
| Daytona | 自定义沙盒管理服务 | 代码执行环境 |
| Firecrawl | 自定义爬虫服务 | 网页内容抓取 |
| 搜索服务 | SearXNG | 聚合搜索引擎 |
| 监控服务 | Prometheus + Grafana | 系统监控 |

### 系统架构

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   前端应用      │    │   后端API       │    │   Worker服务    │
│   (Next.js)     │◄──►│   (FastAPI)     │◄──►│   (Celery)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       ▼                       ▼
         │              ┌─────────────────┐    ┌─────────────────┐
         │              │   PostgreSQL    │    │   RabbitMQ      │
         │              │   + PostgREST   │    │   (消息队列)    │
         │              └─────────────────┘    └─────────────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   实时通信      │    │   认证服务      │    │   对象存储      │
│   (WebSocket)   │    │   (GoTrue)      │    │   (MinIO)       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   沙盒管理      │    │   爬虫服务      │    │   搜索服务      │
│   (Docker)      │    │   (Playwright)  │    │   (SearXNG)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Redis缓存     │    │   Prometheus    │    │   Grafana       │
│   (缓存/会话)   │    │   (监控指标)    │    │   (监控面板)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🚀 快速开始

### 前置要求

- **Docker**: 版本 20.10+
- **Docker Compose**: 版本 2.0+
- **Python**: 版本 3.9+
- **Node.js**: 版本 16+ (如果需要前端)
- **Git**: 用于克隆代码

### 安装步骤

1. **克隆项目**
   ```bash
   git clone <repository-url>
   cd suna
   ```

2. **安装Python依赖**
   ```bash
   # 安装启动脚本依赖
   pip install -r scripts/requirements.txt
   
   # 安装后端依赖
   pip install -r backend/requirements.txt
   
   # 安装各服务依赖
   pip install -r services/sandbox_manager/requirements.txt
   pip install -r services/crawler/requirements.txt
   pip install -r services/realtime/requirements.txt
   ```

3. **配置环境变量**
   ```bash
   # 复制环境变量文件
   cp .env.opensource .env
   
   # 根据需要修改配置
   nano .env
   ```

4. **启动所有服务**
   ```bash
   python scripts/start-opensource.py start
   ```

### 一键启动

我们提供了智能启动脚本，可以自动检查依赖、启动服务并显示状态：

```bash
# 启动所有服务
python scripts/start-opensource.py start

# 查看服务状态
python scripts/start-opensource.py status

# 查看服务日志
python scripts/start-opensource.py logs

# 停止所有服务
python scripts/start-opensource.py stop

# 清理所有资源
python scripts/start-opensource.py cleanup
```

## 📋 服务端口

| 服务 | 端口 | 访问地址 | 说明 |
|------|------|----------|------|
| 前端应用 | 3001 | http://localhost:3001 | 主应用界面 |
| 后端API | 8000 | http://localhost:8000 | API服务 |
| API文档 | 8000 | http://localhost:8000/docs | Swagger文档 |
| PostgreSQL | 5432 | localhost:5432 | 数据库 |
| PostgREST | 3001 | http://localhost:3001 | REST API |
| GoTrue | 9999 | http://localhost:9999 | 认证服务 |
| MinIO | 9000 | http://localhost:9000 | 对象存储 |
| MinIO控制台 | 9001 | http://localhost:9001 | 存储管理 |
| Redis | 6379 | localhost:6379 | 缓存服务 |
| RabbitMQ | 5672 | localhost:5672 | 消息队列 |
| RabbitMQ管理 | 15672 | http://localhost:15672 | 队列管理 |
| 沙盒管理 | 8001 | http://localhost:8001 | 代码执行 |
| 爬虫服务 | 8002 | http://localhost:8002 | 网页抓取 |
| 实时通信 | 8003 | ws://localhost:8003 | WebSocket |
| SearXNG | 8080 | http://localhost:8080 | 搜索引擎 |
| Prometheus | 9090 | http://localhost:9090 | 监控指标 |
| Grafana | 3000 | http://localhost:3000 | 监控面板 |

## 🔧 配置说明

### 环境变量

主要配置文件：`.env.opensource`

```bash
# 数据库配置
POSTGRES_DB=suna_db
POSTGRES_USER=suna_app
POSTGRES_PASSWORD=suna_password

# 认证配置
GOTRUE_JWT_SECRET=your-jwt-secret
GOTRUE_JWT_EXP=3600

# 存储配置
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin

# Redis配置
REDIS_PASSWORD=redis_password

# RabbitMQ配置
RABBITMQ_DEFAULT_USER=guest
RABBITMQ_DEFAULT_PASS=guest
```

### 数据库初始化

数据库会在首次启动时自动初始化，包括：
- 创建必要的表结构
- 设置用户角色和权限
- 配置行级安全策略
- 插入初始数据

### 服务配置

每个自定义服务都有独立的配置：

- **沙盒管理服务**: `services/sandbox_manager/`
- **爬虫服务**: `services/crawler/`
- **实时通信服务**: `services/realtime/`

## 🛠️ 开发指南

### 项目结构

```
suna/
├── backend/                 # 后端API服务
│   ├── services/           # 服务适配器
│   │   ├── database.py     # 数据库服务
│   │   ├── auth.py         # 认证服务
│   │   └── storage.py      # 存储服务
│   ├── main.py             # API入口
│   └── requirements.txt    # Python依赖
├── services/               # 自定义微服务
│   ├── sandbox_manager/    # 沙盒管理服务
│   ├── crawler/            # 爬虫服务
│   └── realtime/           # 实时通信服务
├── database/               # 数据库相关
│   └── init.sql            # 初始化脚本
├── scripts/                # 管理脚本
│   └── start-opensource.py # 启动脚本
├── docker-compose.opensource.yml # Docker配置
├── .env.opensource         # 环境变量
└── README.opensource.md    # 本文档
```

### 添加新服务

1. **创建服务目录**
   ```bash
   mkdir services/new_service
   cd services/new_service
   ```

2. **创建服务代码**
   ```python
   # main.py
   from fastapi import FastAPI
   
   app = FastAPI(title="New Service")
   
   @app.get("/health")
   async def health_check():
       return {"status": "healthy"}
   ```

3. **添加依赖文件**
   ```bash
   echo "fastapi\nuvicorn" > requirements.txt
   ```

4. **更新Docker配置**
   在 `docker-compose.opensource.yml` 中添加服务定义

5. **更新启动脚本**
   在 `scripts/start-opensource.py` 中添加服务启动逻辑

### 数据库迁移

如需修改数据库结构：

1. **修改初始化脚本**
   编辑 `database/init.sql`

2. **重新初始化数据库**
   ```bash
   python scripts/start-opensource.py cleanup
   python scripts/start-opensource.py start
   ```

### API开发

后端API使用FastAPI框架，支持：
- 自动API文档生成
- 数据验证
- 异步处理
- 依赖注入

访问 http://localhost:8000/docs 查看API文档。

## 🔍 监控和日志

### Prometheus监控

访问 http://localhost:9090 查看监控指标，包括：
- 系统资源使用情况
- 服务健康状态
- API请求统计
- 数据库性能指标

### Grafana仪表板

访问 http://localhost:3000 查看可视化监控面板：
- 默认用户名/密码：admin/admin
- 预配置的仪表板
- 实时性能图表
- 告警配置

### 日志查看

```bash
# 查看所有服务日志
python scripts/start-opensource.py logs

# 查看特定服务日志
docker-compose -f docker-compose.opensource.yml logs -f postgres
docker-compose -f docker-compose.opensource.yml logs -f api
```

## 🚨 故障排除

### 常见问题

1. **Docker启动失败**
   ```bash
   # 检查Docker状态
   docker --version
   docker-compose --version
   
   # 重启Docker服务
   sudo systemctl restart docker
   ```

2. **端口冲突**
   ```bash
   # 检查端口占用
   netstat -tulpn | grep :8000
   
   # 修改配置文件中的端口
   nano .env.opensource
   ```

3. **数据库连接失败**
   ```bash
   # 检查数据库状态
   docker-compose -f docker-compose.opensource.yml ps postgres
   
   # 查看数据库日志
   docker-compose -f docker-compose.opensource.yml logs postgres
   ```

4. **服务启动超时**
   ```bash
   # 增加启动等待时间
   # 编辑 scripts/start-opensource.py 中的 max_attempts
   ```

### 性能优化

1. **数据库优化**
   - 调整PostgreSQL配置
   - 添加适当的索引
   - 优化查询语句

2. **缓存优化**
   - 配置Redis缓存策略
   - 使用连接池
   - 实现查询缓存

3. **资源限制**
   - 在docker-compose.yml中设置资源限制
   - 监控内存和CPU使用情况
   - 调整并发连接数

## 🔐 安全配置

### 生产环境部署

1. **修改默认密码**
   ```bash
   # 修改所有默认密码
   nano .env.opensource
   ```

2. **启用HTTPS**
   - 配置SSL证书
   - 使用反向代理（Nginx/Traefik）
   - 强制HTTPS重定向

3. **网络安全**
   - 配置防火墙规则
   - 限制外部访问端口
   - 使用VPN或内网部署

4. **数据备份**
   ```bash
   # 数据库备份
   docker-compose -f docker-compose.opensource.yml exec postgres pg_dump -U suna_app suna_db > backup.sql
   
   # 对象存储备份
   docker-compose -f docker-compose.opensource.yml exec minio mc mirror /data /backup
   ```

## 📚 API文档

### 认证API

```bash
# 用户注册
curl -X POST http://localhost:9999/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password123"}'

# 用户登录
curl -X POST http://localhost:9999/token \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password123"}'
```

### 数据库API

```bash
# 查询数据
curl -X GET http://localhost:3001/projects \
  -H "Authorization: Bearer <token>"

# 插入数据
curl -X POST http://localhost:3001/projects \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Project","description":"A test project"}'
```

### 存储API

```bash
# 上传文件
curl -X POST http://localhost:8000/storage/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@example.jpg"

# 下载文件
curl -X GET http://localhost:8000/storage/download/file-id \
  -H "Authorization: Bearer <token>"
```

## 🤝 贡献指南

我们欢迎社区贡献！请遵循以下步骤：

1. **Fork项目**
2. **创建功能分支**
   ```bash
   git checkout -b feature/new-feature
   ```
3. **提交更改**
   ```bash
   git commit -m "Add new feature"
   ```
4. **推送分支**
   ```bash
   git push origin feature/new-feature
   ```
5. **创建Pull Request**

### 代码规范

- Python代码遵循PEP 8规范
- 使用类型注解
- 添加适当的文档字符串
- 编写单元测试

### 测试

```bash
# 运行后端测试
cd backend
pytest

# 运行服务测试
cd services/sandbox_manager
pytest
```

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

## 🙏 致谢

感谢以下开源项目：

- [PostgreSQL](https://postgresql.org/) - 强大的关系型数据库
- [PostgREST](https://postgrest.org/) - 自动生成REST API
- [GoTrue](https://github.com/netlify/gotrue) - 用户认证服务
- [MinIO](https://min.io/) - 高性能对象存储
- [FastAPI](https://fastapi.tiangolo.com/) - 现代Python Web框架
- [Redis](https://redis.io/) - 内存数据库
- [RabbitMQ](https://rabbitmq.com/) - 消息队列
- [SearXNG](https://searxng.org/) - 隐私搜索引擎
- [Prometheus](https://prometheus.io/) - 监控系统
- [Grafana](https://grafana.com/) - 可视化平台

## 📞 支持

如有问题或建议，请：

1. 查看[常见问题](#故障排除)
2. 搜索现有[Issues](https://github.com/your-repo/issues)
3. 创建新的[Issue](https://github.com/your-repo/issues/new)
4. 加入我们的社区讨论

---

**Suna 开源版本** - 让AI助手完全属于你！ 🚀