#!/usr/bin/env python3
"""
Suna 沙盒管理服务
替代 Daytona 的容器管理功能，提供安全的代码执行环境

主要功能：
- 创建和管理 Docker 容器
- 提供安全的代码执行环境
- 文件系统隔离
- 网络隔离
- 资源限制
- 容器生命周期管理
"""

import asyncio
import json
import logging
import os
import tempfile
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

import aiofiles
import docker
from docker.errors import DockerException, NotFound, APIError
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 配置
class Config:
    # 服务配置
    HOST = os.getenv('SANDBOX_HOST', '0.0.0.0')
    PORT = int(os.getenv('SANDBOX_PORT', 8001))
    
    # Docker 配置
    SANDBOX_IMAGE = os.getenv('SANDBOX_IMAGE', 'python:3.11-slim')
    MAX_CONTAINERS = int(os.getenv('MAX_SANDBOX_CONTAINERS', 10))
    CONTAINER_TIMEOUT = int(os.getenv('SANDBOX_TIMEOUT', 3600))  # 1小时
    NETWORK_NAME = os.getenv('SANDBOX_NETWORK', 'suna-sandbox-network')
    
    # 资源限制
    MEMORY_LIMIT = os.getenv('SANDBOX_MEMORY_LIMIT', '512m')
    CPU_LIMIT = float(os.getenv('SANDBOX_CPU_LIMIT', '1.0'))
    
    # 安全配置
    ALLOWED_ORIGINS = os.getenv('CORS_ORIGINS', 'http://localhost:3000,http://localhost:8000').split(',')
    
    # 工作目录
    WORK_DIR = Path(os.getenv('SANDBOX_WORK_DIR', '/tmp/suna_sandbox'))
    WORK_DIR.mkdir(exist_ok=True)

# Pydantic 模型
class SandboxCreateRequest(BaseModel):
    """创建沙盒请求"""
    image: Optional[str] = Field(default=None, description="Docker 镜像名称")
    command: Optional[List[str]] = Field(default=None, description="启动命令")
    environment: Optional[Dict[str, str]] = Field(default_factory=dict, description="环境变量")
    working_dir: Optional[str] = Field(default="/workspace", description="工作目录")
    timeout: Optional[int] = Field(default=None, description="超时时间（秒）")
    memory_limit: Optional[str] = Field(default=None, description="内存限制")
    cpu_limit: Optional[float] = Field(default=None, description="CPU 限制")
    volumes: Optional[Dict[str, str]] = Field(default_factory=dict, description="卷挂载")
    network_disabled: bool = Field(default=False, description="是否禁用网络")

class SandboxExecuteRequest(BaseModel):
    """执行命令请求"""
    command: List[str] = Field(..., description="要执行的命令")
    working_dir: Optional[str] = Field(default=None, description="工作目录")
    environment: Optional[Dict[str, str]] = Field(default_factory=dict, description="环境变量")
    timeout: Optional[int] = Field(default=30, description="超时时间（秒）")
    user: Optional[str] = Field(default=None, description="执行用户")

class FileUploadRequest(BaseModel):
    """文件上传请求"""
    path: str = Field(..., description="文件路径")
    content: str = Field(..., description="文件内容（base64 编码）")
    encoding: str = Field(default="utf-8", description="文件编码")
    mode: Optional[str] = Field(default="644", description="文件权限")

class SandboxInfo(BaseModel):
    """沙盒信息"""
    id: str
    status: str
    image: str
    created_at: datetime
    expires_at: datetime
    ports: Dict[str, int]
    volumes: Dict[str, str]
    environment: Dict[str, str]
    resource_usage: Optional[Dict[str, Any]] = None

class ExecutionResult(BaseModel):
    """执行结果"""
    exit_code: int
    stdout: str
    stderr: str
    execution_time: float
    timeout: bool = False

# 沙盒管理器
class SandboxManager:
    """沙盒管理器"""
    
    def __init__(self):
        self.docker_client = docker.from_env()
        self.containers: Dict[str, Dict] = {}
        self.cleanup_task = None
        
        # 确保网络存在
        self._ensure_network()
        
        # 启动清理任务
        self.cleanup_task = asyncio.create_task(self._cleanup_expired_containers())
    
    def _ensure_network(self):
        """确保沙盒网络存在"""
        try:
            self.docker_client.networks.get(Config.NETWORK_NAME)
            logger.info(f"网络 {Config.NETWORK_NAME} 已存在")
        except NotFound:
            logger.info(f"创建网络 {Config.NETWORK_NAME}")
            self.docker_client.networks.create(
                Config.NETWORK_NAME,
                driver="bridge",
                options={
                    "com.docker.network.bridge.enable_icc": "false",
                    "com.docker.network.bridge.enable_ip_masquerade": "true"
                }
            )
    
    async def create_sandbox(
        self, 
        request: SandboxCreateRequest
    ) -> str:
        """创建新的沙盒容器"""
        
        # 检查容器数量限制
        if len(self.containers) >= Config.MAX_CONTAINERS:
            raise HTTPException(
                status_code=429, 
                detail=f"已达到最大容器数量限制 ({Config.MAX_CONTAINERS})"
            )
        
        sandbox_id = str(uuid.uuid4())
        image = request.image or Config.SANDBOX_IMAGE
        timeout = request.timeout or Config.CONTAINER_TIMEOUT
        
        try:
            # 创建工作目录
            work_dir = Config.WORK_DIR / sandbox_id
            work_dir.mkdir(exist_ok=True)
            
            # 准备容器配置
            container_config = {
                'image': image,
                'detach': True,
                'name': f"suna-sandbox-{sandbox_id}",
                'working_dir': request.working_dir,
                'environment': {
                    'SANDBOX_ID': sandbox_id,
                    'PYTHONUNBUFFERED': '1',
                    **request.environment
                },
                'volumes': {
                    str(work_dir): {'bind': '/workspace', 'mode': 'rw'},
                    **request.volumes
                },
                'mem_limit': request.memory_limit or Config.MEMORY_LIMIT,
                'cpu_period': 100000,
                'cpu_quota': int((request.cpu_limit or Config.CPU_LIMIT) * 100000),
                'network_mode': None if request.network_disabled else Config.NETWORK_NAME,
                'security_opt': ['no-new-privileges:true'],
                'cap_drop': ['ALL'],
                'cap_add': ['CHOWN', 'DAC_OVERRIDE', 'FOWNER', 'SETGID', 'SETUID'],
                'read_only': False,
                'tmpfs': {
                    '/tmp': 'noexec,nosuid,size=100m',
                    '/var/tmp': 'noexec,nosuid,size=100m'
                },
                'ulimits': [
                    docker.types.Ulimit(name='nproc', soft=1024, hard=1024),
                    docker.types.Ulimit(name='nofile', soft=1024, hard=1024)
                ]
            }
            
            # 如果指定了启动命令
            if request.command:
                container_config['command'] = request.command
            else:
                # 默认保持容器运行
                container_config['command'] = ['sleep', 'infinity']
            
            # 创建容器
            logger.info(f"创建沙盒容器 {sandbox_id}，镜像: {image}")
            container = self.docker_client.containers.run(**container_config)
            
            # 记录容器信息
            expires_at = datetime.now() + timedelta(seconds=timeout)
            self.containers[sandbox_id] = {
                'container': container,
                'created_at': datetime.now(),
                'expires_at': expires_at,
                'image': image,
                'work_dir': work_dir,
                'config': request.dict()
            }
            
            logger.info(f"沙盒容器 {sandbox_id} 创建成功")
            return sandbox_id
            
        except DockerException as e:
            logger.error(f"创建沙盒容器失败: {e}")
            raise HTTPException(status_code=500, detail=f"创建容器失败: {str(e)}")
    
    async def get_sandbox_info(self, sandbox_id: str) -> SandboxInfo:
        """获取沙盒信息"""
        if sandbox_id not in self.containers:
            raise HTTPException(status_code=404, detail="沙盒不存在")
        
        container_info = self.containers[sandbox_id]
        container = container_info['container']
        
        try:
            # 刷新容器状态
            container.reload()
            
            # 获取端口映射
            ports = {}
            if container.attrs.get('NetworkSettings', {}).get('Ports'):
                for container_port, host_info in container.attrs['NetworkSettings']['Ports'].items():
                    if host_info:
                        ports[container_port] = int(host_info[0]['HostPort'])
            
            # 获取资源使用情况
            resource_usage = None
            try:
                stats = container.stats(stream=False)
                resource_usage = {
                    'cpu_usage': stats.get('cpu_stats', {}),
                    'memory_usage': stats.get('memory_stats', {}),
                    'network_usage': stats.get('networks', {})
                }
            except Exception as e:
                logger.warning(f"获取容器 {sandbox_id} 资源使用情况失败: {e}")
            
            return SandboxInfo(
                id=sandbox_id,
                status=container.status,
                image=container_info['image'],
                created_at=container_info['created_at'],
                expires_at=container_info['expires_at'],
                ports=ports,
                volumes=container_info['config'].get('volumes', {}),
                environment=container_info['config'].get('environment', {}),
                resource_usage=resource_usage
            )
            
        except DockerException as e:
            logger.error(f"获取沙盒 {sandbox_id} 信息失败: {e}")
            raise HTTPException(status_code=500, detail=f"获取容器信息失败: {str(e)}")
    
    async def execute_command(
        self, 
        sandbox_id: str, 
        request: SandboxExecuteRequest
    ) -> ExecutionResult:
        """在沙盒中执行命令"""
        if sandbox_id not in self.containers:
            raise HTTPException(status_code=404, detail="沙盒不存在")
        
        container = self.containers[sandbox_id]['container']
        
        try:
            # 检查容器状态
            container.reload()
            if container.status != 'running':
                raise HTTPException(status_code=400, detail=f"容器状态异常: {container.status}")
            
            start_time = time.time()
            
            # 准备执行配置
            exec_config = {
                'cmd': request.command,
                'stdout': True,
                'stderr': True,
                'stdin': False,
                'tty': False,
                'privileged': False,
                'user': request.user or 'root',
                'environment': request.environment,
                'workdir': request.working_dir
            }
            
            # 创建执行实例
            exec_instance = container.client.api.exec_create(
                container.id, 
                **exec_config
            )
            
            # 执行命令
            logger.info(f"在沙盒 {sandbox_id} 中执行命令: {' '.join(request.command)}")
            
            # 使用超时执行
            try:
                output = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: container.client.api.exec_start(
                            exec_instance['Id'],
                            stream=False,
                            socket=False
                        )
                    ),
                    timeout=request.timeout
                )
                
                # 获取执行结果
                exec_result = container.client.api.exec_inspect(exec_instance['Id'])
                exit_code = exec_result['ExitCode']
                
                execution_time = time.time() - start_time
                
                # 解析输出
                if isinstance(output, bytes):
                    output_str = output.decode('utf-8', errors='replace')
                else:
                    output_str = str(output)
                
                # 简单分离 stdout 和 stderr（Docker API 限制）
                stdout = output_str
                stderr = ""
                
                return ExecutionResult(
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    execution_time=execution_time,
                    timeout=False
                )
                
            except asyncio.TimeoutError:
                logger.warning(f"沙盒 {sandbox_id} 命令执行超时")
                execution_time = time.time() - start_time
                
                return ExecutionResult(
                    exit_code=-1,
                    stdout="",
                    stderr="命令执行超时",
                    execution_time=execution_time,
                    timeout=True
                )
                
        except DockerException as e:
            logger.error(f"在沙盒 {sandbox_id} 中执行命令失败: {e}")
            raise HTTPException(status_code=500, detail=f"执行命令失败: {str(e)}")
    
    async def upload_file(
        self, 
        sandbox_id: str, 
        request: FileUploadRequest
    ) -> Dict[str, str]:
        """上传文件到沙盒"""
        if sandbox_id not in self.containers:
            raise HTTPException(status_code=404, detail="沙盒不存在")
        
        container_info = self.containers[sandbox_id]
        work_dir = container_info['work_dir']
        
        try:
            import base64
            
            # 解码文件内容
            if request.content.startswith('data:'):
                # 处理 data URL
                header, data = request.content.split(',', 1)
                file_content = base64.b64decode(data)
            else:
                # 直接 base64 解码
                file_content = base64.b64decode(request.content)
            
            # 确保目标目录存在
            file_path = work_dir / request.path.lstrip('/')
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(file_content)
            
            # 设置文件权限
            if request.mode:
                os.chmod(file_path, int(request.mode, 8))
            
            logger.info(f"文件上传到沙盒 {sandbox_id}: {request.path}")
            
            return {
                'path': request.path,
                'size': len(file_content),
                'status': 'uploaded'
            }
            
        except Exception as e:
            logger.error(f"上传文件到沙盒 {sandbox_id} 失败: {e}")
            raise HTTPException(status_code=500, detail=f"上传文件失败: {str(e)}")
    
    async def download_file(self, sandbox_id: str, file_path: str) -> bytes:
        """从沙盒下载文件"""
        if sandbox_id not in self.containers:
            raise HTTPException(status_code=404, detail="沙盒不存在")
        
        container_info = self.containers[sandbox_id]
        work_dir = container_info['work_dir']
        
        try:
            full_path = work_dir / file_path.lstrip('/')
            
            if not full_path.exists():
                raise HTTPException(status_code=404, detail="文件不存在")
            
            async with aiofiles.open(full_path, 'rb') as f:
                content = await f.read()
            
            logger.info(f"从沙盒 {sandbox_id} 下载文件: {file_path}")
            return content
            
        except Exception as e:
            logger.error(f"从沙盒 {sandbox_id} 下载文件失败: {e}")
            raise HTTPException(status_code=500, detail=f"下载文件失败: {str(e)}")
    
    async def list_sandboxes(self) -> List[SandboxInfo]:
        """列出所有沙盒"""
        sandboxes = []
        
        for sandbox_id in list(self.containers.keys()):
            try:
                info = await self.get_sandbox_info(sandbox_id)
                sandboxes.append(info)
            except Exception as e:
                logger.warning(f"获取沙盒 {sandbox_id} 信息失败: {e}")
                continue
        
        return sandboxes
    
    async def delete_sandbox(self, sandbox_id: str) -> Dict[str, str]:
        """删除沙盒"""
        if sandbox_id not in self.containers:
            raise HTTPException(status_code=404, detail="沙盒不存在")
        
        container_info = self.containers[sandbox_id]
        container = container_info['container']
        work_dir = container_info['work_dir']
        
        try:
            # 停止并删除容器
            logger.info(f"删除沙盒容器 {sandbox_id}")
            container.stop(timeout=10)
            container.remove()
            
            # 清理工作目录
            import shutil
            if work_dir.exists():
                shutil.rmtree(work_dir)
            
            # 从记录中移除
            del self.containers[sandbox_id]
            
            logger.info(f"沙盒 {sandbox_id} 删除成功")
            
            return {
                'sandbox_id': sandbox_id,
                'status': 'deleted'
            }
            
        except DockerException as e:
            logger.error(f"删除沙盒 {sandbox_id} 失败: {e}")
            raise HTTPException(status_code=500, detail=f"删除容器失败: {str(e)}")
    
    async def _cleanup_expired_containers(self):
        """清理过期的容器"""
        while True:
            try:
                now = datetime.now()
                expired_containers = []
                
                for sandbox_id, container_info in self.containers.items():
                    if now > container_info['expires_at']:
                        expired_containers.append(sandbox_id)
                
                for sandbox_id in expired_containers:
                    try:
                        await self.delete_sandbox(sandbox_id)
                        logger.info(f"清理过期沙盒: {sandbox_id}")
                    except Exception as e:
                        logger.error(f"清理过期沙盒 {sandbox_id} 失败: {e}")
                
                # 每分钟检查一次
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"清理任务异常: {e}")
                await asyncio.sleep(60)
    
    async def cleanup(self):
        """清理资源"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
        
        # 清理所有容器
        for sandbox_id in list(self.containers.keys()):
            try:
                await self.delete_sandbox(sandbox_id)
            except Exception as e:
                logger.error(f"清理沙盒 {sandbox_id} 失败: {e}")
        
        # 关闭 Docker 客户端
        self.docker_client.close()

# 全局沙盒管理器实例
sandbox_manager = SandboxManager()

# FastAPI 应用
app = FastAPI(
    title="Suna 沙盒管理服务",
    description="提供安全的代码执行环境",
    version="1.0.0"
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由
@app.post("/sandboxes", response_model=Dict[str, str])
async def create_sandbox(request: SandboxCreateRequest):
    """创建新的沙盒"""
    sandbox_id = await sandbox_manager.create_sandbox(request)
    return {"sandbox_id": sandbox_id, "status": "created"}

@app.get("/sandboxes", response_model=List[SandboxInfo])
async def list_sandboxes():
    """列出所有沙盒"""
    return await sandbox_manager.list_sandboxes()

@app.get("/sandboxes/{sandbox_id}", response_model=SandboxInfo)
async def get_sandbox(sandbox_id: str):
    """获取沙盒信息"""
    return await sandbox_manager.get_sandbox_info(sandbox_id)

@app.post("/sandboxes/{sandbox_id}/execute", response_model=ExecutionResult)
async def execute_command(sandbox_id: str, request: SandboxExecuteRequest):
    """在沙盒中执行命令"""
    return await sandbox_manager.execute_command(sandbox_id, request)

@app.post("/sandboxes/{sandbox_id}/files", response_model=Dict[str, str])
async def upload_file(sandbox_id: str, request: FileUploadRequest):
    """上传文件到沙盒"""
    return await sandbox_manager.upload_file(sandbox_id, request)

@app.get("/sandboxes/{sandbox_id}/files/{file_path:path}")
async def download_file(sandbox_id: str, file_path: str):
    """从沙盒下载文件"""
    from fastapi.responses import Response
    
    content = await sandbox_manager.download_file(sandbox_id, file_path)
    
    # 根据文件扩展名设置 MIME 类型
    import mimetypes
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = 'application/octet-stream'
    
    return Response(content=content, media_type=mime_type)

@app.delete("/sandboxes/{sandbox_id}", response_model=Dict[str, str])
async def delete_sandbox(sandbox_id: str):
    """删除沙盒"""
    return await sandbox_manager.delete_sandbox(sandbox_id)

@app.get("/health")
async def health_check():
    """健康检查"""
    try:
        # 检查 Docker 连接
        sandbox_manager.docker_client.ping()
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "containers": len(sandbox_manager.containers),
            "max_containers": Config.MAX_CONTAINERS
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"服务不健康: {str(e)}")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理资源"""
    logger.info("正在关闭沙盒管理服务...")
    await sandbox_manager.cleanup()
    logger.info("沙盒管理服务已关闭")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=Config.HOST,
        port=Config.PORT,
        reload=True,
        log_level="info"
    )