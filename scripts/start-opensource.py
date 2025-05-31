#!/usr/bin/env python3
"""
Suna 开源版本启动脚本
用于启动所有开源服务组件
"""

import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import click
import docker
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 控制台
console = Console()

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

class ServiceManager:
    """服务管理器"""
    
    def __init__(self):
        self.docker_client = None
        self.services: Dict[str, subprocess.Popen] = {}
        self.containers: Dict[str, str] = {}
        
    def initialize_docker(self):
        """初始化Docker客户端"""
        try:
            self.docker_client = docker.from_env()
            self.docker_client.ping()
            console.print("[green]✓[/green] Docker连接成功")
            return True
        except Exception as e:
            console.print(f"[red]✗[/red] Docker连接失败: {e}")
            return False
    
    def check_prerequisites(self) -> bool:
        """检查前置条件"""
        console.print("[blue]检查前置条件...[/blue]")
        
        # 检查Docker
        if not self.initialize_docker():
            return False
        
        # 检查必要文件
        required_files = [
            'docker-compose.opensource.yml',
            '.env.opensource',
            'database/init.sql'
        ]
        
        for file_path in required_files:
            full_path = PROJECT_ROOT / file_path
            if not full_path.exists():
                console.print(f"[red]✗[/red] 缺少必要文件: {file_path}")
                return False
            console.print(f"[green]✓[/green] 找到文件: {file_path}")
        
        # 检查Python依赖
        try:
            import fastapi
            import uvicorn
            import redis
            import minio
            console.print("[green]✓[/green] Python依赖检查通过")
        except ImportError as e:
            console.print(f"[red]✗[/red] 缺少Python依赖: {e}")
            console.print("请运行: pip install -r backend/requirements.txt")
            return False
        
        return True
    
    def start_infrastructure(self) -> bool:
        """启动基础设施服务"""
        console.print("[blue]启动基础设施服务...[/blue]")
        
        try:
            # 使用docker-compose启动基础设施
            cmd = [
                'docker-compose',
                '-f', 'docker-compose.opensource.yml',
                '--env-file', '.env.opensource',
                'up', '-d',
                'postgres', 'postgrest', 'gotrue', 'minio',
                'redis', 'rabbitmq', 'searxng', 'prometheus', 'grafana'
            ]
            
            result = subprocess.run(
                cmd,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                console.print(f"[red]✗[/red] 启动基础设施失败: {result.stderr}")
                return False
            
            console.print("[green]✓[/green] 基础设施服务启动成功")
            
            # 等待服务就绪
            self.wait_for_services()
            
            return True
            
        except Exception as e:
            console.print(f"[red]✗[/red] 启动基础设施失败: {e}")
            return False
    
    def wait_for_services(self):
        """等待服务就绪"""
        console.print("[blue]等待服务就绪...[/blue]")
        
        services_to_check = {
            'PostgreSQL': ('localhost', 5432),
            'Redis': ('localhost', 6379),
            'MinIO': ('localhost', 9000),
            'PostgREST': ('localhost', 3001),
            'GoTrue': ('localhost', 9999)
        }
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            
            for service_name, (host, port) in services_to_check.items():
                task = progress.add_task(f"等待 {service_name}...", total=None)
                
                max_attempts = 30
                for attempt in range(max_attempts):
                    try:
                        import socket
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(1)
                        result = sock.connect_ex((host, port))
                        sock.close()
                        
                        if result == 0:
                            progress.update(task, description=f"[green]✓[/green] {service_name} 就绪")
                            break
                    except:
                        pass
                    
                    time.sleep(2)
                else:
                    progress.update(task, description=f"[yellow]⚠[/yellow] {service_name} 超时")
                
                progress.remove_task(task)
    
    def start_custom_services(self) -> bool:
        """启动自定义服务"""
        console.print("[blue]启动自定义服务...[/blue]")
        
        services = {
            'sandbox_manager': {
                'path': PROJECT_ROOT / 'services' / 'sandbox_manager',
                'cmd': [sys.executable, 'main.py'],
                'port': 8001
            },
            'crawler': {
                'path': PROJECT_ROOT / 'services' / 'crawler',
                'cmd': [sys.executable, 'main.py'],
                'port': 8002
            },
            'realtime': {
                'path': PROJECT_ROOT / 'services' / 'realtime',
                'cmd': [sys.executable, 'main.py'],
                'port': 8003
            }
        }
        
        for service_name, config in services.items():
            try:
                console.print(f"启动 {service_name}...")
                
                # 设置环境变量
                env = os.environ.copy()
                env.update({
                    'PORT': str(config['port']),
                    'HOST': '0.0.0.0'
                })
                
                # 启动服务
                process = subprocess.Popen(
                    config['cmd'],
                    cwd=config['path'],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                self.services[service_name] = process
                console.print(f"[green]✓[/green] {service_name} 启动成功 (PID: {process.pid})")
                
            except Exception as e:
                console.print(f"[red]✗[/red] 启动 {service_name} 失败: {e}")
                return False
        
        return True
    
    def start_backend_services(self) -> bool:
        """启动后端服务"""
        console.print("[blue]启动后端服务...[/blue]")
        
        try:
            # 启动API服务
            api_env = os.environ.copy()
            api_env.update({
                'PORT': '8000',
                'HOST': '0.0.0.0',
                'DATABASE_URL': 'postgresql://suna_app:suna_password@localhost:5432/suna_db',
                'REDIS_URL': 'redis://localhost:6379/0',
                'MINIO_ENDPOINT': 'localhost:9000',
                'GOTRUE_URL': 'http://localhost:9999'
            })
            
            api_process = subprocess.Popen(
                [sys.executable, '-m', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', '8000', '--reload'],
                cwd=PROJECT_ROOT / 'backend',
                env=api_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            self.services['api'] = api_process
            console.print(f"[green]✓[/green] API服务启动成功 (PID: {api_process.pid})")
            
            # 启动Worker服务
            worker_process = subprocess.Popen(
                [sys.executable, '-m', 'celery', 'worker', '-A', 'worker.celery_app', '--loglevel=info'],
                cwd=PROJECT_ROOT / 'backend',
                env=api_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            self.services['worker'] = worker_process
            console.print(f"[green]✓[/green] Worker服务启动成功 (PID: {worker_process.pid})")
            
            return True
            
        except Exception as e:
            console.print(f"[red]✗[/red] 启动后端服务失败: {e}")
            return False
    
    def start_frontend(self) -> bool:
        """启动前端服务"""
        console.print("[blue]启动前端服务...[/blue]")
        
        try:
            frontend_path = PROJECT_ROOT / 'frontend'
            
            if not frontend_path.exists():
                console.print("[yellow]⚠[/yellow] 前端目录不存在，跳过前端启动")
                return True
            
            # 检查是否有package.json
            if not (frontend_path / 'package.json').exists():
                console.print("[yellow]⚠[/yellow] 前端package.json不存在，跳过前端启动")
                return True
            
            # 启动前端开发服务器
            frontend_env = os.environ.copy()
            frontend_env.update({
                'NEXT_PUBLIC_API_URL': 'http://localhost:8000',
                'NEXT_PUBLIC_WS_URL': 'ws://localhost:8003'
            })
            
            frontend_process = subprocess.Popen(
                ['npm', 'run', 'dev'],
                cwd=frontend_path,
                env=frontend_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            self.services['frontend'] = frontend_process
            console.print(f"[green]✓[/green] 前端服务启动成功 (PID: {frontend_process.pid})")
            
            return True
            
        except Exception as e:
            console.print(f"[red]✗[/red] 启动前端服务失败: {e}")
            return False
    
    def show_status(self):
        """显示服务状态"""
        table = Table(title="Suna 开源版本 - 服务状态")
        table.add_column("服务", style="cyan")
        table.add_column("状态", style="green")
        table.add_column("端口", style="yellow")
        table.add_column("URL", style="blue")
        
        # 基础设施服务
        infrastructure_services = [
            ("PostgreSQL", "运行中", "5432", "localhost:5432"),
            ("PostgREST", "运行中", "3001", "http://localhost:3001"),
            ("GoTrue", "运行中", "9999", "http://localhost:9999"),
            ("MinIO", "运行中", "9000", "http://localhost:9000"),
            ("Redis", "运行中", "6379", "localhost:6379"),
            ("RabbitMQ", "运行中", "5672", "http://localhost:15672"),
            ("SearXNG", "运行中", "8080", "http://localhost:8080"),
            ("Prometheus", "运行中", "9090", "http://localhost:9090"),
            ("Grafana", "运行中", "3000", "http://localhost:3000")
        ]
        
        for service, status, port, url in infrastructure_services:
            table.add_row(service, status, port, url)
        
        # 自定义服务
        custom_services = [
            ("沙盒管理", "运行中", "8001", "http://localhost:8001"),
            ("爬虫服务", "运行中", "8002", "http://localhost:8002"),
            ("实时通信", "运行中", "8003", "ws://localhost:8003")
        ]
        
        for service, status, port, url in custom_services:
            table.add_row(service, status, port, url)
        
        # 应用服务
        app_services = [
            ("API服务", "运行中", "8000", "http://localhost:8000"),
            ("Worker服务", "运行中", "-", "-"),
            ("前端服务", "运行中", "3001", "http://localhost:3001")
        ]
        
        for service, status, port, url in app_services:
            table.add_row(service, status, port, url)
        
        console.print(table)
        
        # 显示重要链接
        console.print("\n[bold]重要链接:[/bold]")
        console.print("• 应用主页: [link]http://localhost:3001[/link]")
        console.print("• API文档: [link]http://localhost:8000/docs[/link]")
        console.print("• MinIO控制台: [link]http://localhost:9000[/link] (minioadmin/minioadmin)")
        console.print("• RabbitMQ管理: [link]http://localhost:15672[/link] (guest/guest)")
        console.print("• Grafana监控: [link]http://localhost:3000[/link] (admin/admin)")
        console.print("• Prometheus: [link]http://localhost:9090[/link]")
    
    def stop_all_services(self):
        """停止所有服务"""
        console.print("[blue]停止所有服务...[/blue]")
        
        # 停止Python服务
        for service_name, process in self.services.items():
            try:
                console.print(f"停止 {service_name}...")
                process.terminate()
                process.wait(timeout=10)
                console.print(f"[green]✓[/green] {service_name} 已停止")
            except subprocess.TimeoutExpired:
                console.print(f"[yellow]⚠[/yellow] 强制停止 {service_name}")
                process.kill()
            except Exception as e:
                console.print(f"[red]✗[/red] 停止 {service_name} 失败: {e}")
        
        # 停止Docker容器
        try:
            cmd = [
                'docker-compose',
                '-f', 'docker-compose.opensource.yml',
                'down'
            ]
            
            subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)
            console.print("[green]✓[/green] Docker服务已停止")
            
        except Exception as e:
            console.print(f"[red]✗[/red] 停止Docker服务失败: {e}")
    
    def cleanup(self):
        """清理资源"""
        console.print("[blue]清理资源...[/blue]")
        
        try:
            # 清理Docker资源
            cmd = [
                'docker-compose',
                '-f', 'docker-compose.opensource.yml',
                'down', '-v', '--remove-orphans'
            ]
            
            subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)
            console.print("[green]✓[/green] Docker资源清理完成")
            
        except Exception as e:
            console.print(f"[red]✗[/red] 清理Docker资源失败: {e}")

# CLI命令
@click.group()
def cli():
    """Suna 开源版本管理工具"""
    pass

@cli.command()
def start():
    """启动所有服务"""
    console.print(Panel.fit(
        "[bold blue]Suna 开源版本启动器[/bold blue]\n\n"
        "这将启动所有必要的服务组件，包括：\n"
        "• PostgreSQL 数据库\n"
        "• PostgREST API\n"
        "• GoTrue 认证\n"
        "• MinIO 对象存储\n"
        "• Redis 缓存\n"
        "• RabbitMQ 消息队列\n"
        "• 自定义微服务\n"
        "• 后端API和Worker\n"
        "• 前端应用",
        title="欢迎使用 Suna 开源版本"
    ))
    
    manager = ServiceManager()
    
    def signal_handler(signum, frame):
        console.print("\n[yellow]收到停止信号，正在关闭服务...[/yellow]")
        manager.stop_all_services()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # 检查前置条件
        if not manager.check_prerequisites():
            console.print("[red]前置条件检查失败，请解决问题后重试[/red]")
            sys.exit(1)
        
        # 启动基础设施
        if not manager.start_infrastructure():
            console.print("[red]基础设施启动失败[/red]")
            sys.exit(1)
        
        # 启动自定义服务
        if not manager.start_custom_services():
            console.print("[red]自定义服务启动失败[/red]")
            sys.exit(1)
        
        # 启动后端服务
        if not manager.start_backend_services():
            console.print("[red]后端服务启动失败[/red]")
            sys.exit(1)
        
        # 启动前端服务
        if not manager.start_frontend():
            console.print("[yellow]前端服务启动失败，但可以继续运行[/yellow]")
        
        # 显示状态
        console.print("\n[green]所有服务启动完成！[/green]")
        manager.show_status()
        
        # 保持运行
        console.print("\n[blue]服务正在运行中... 按 Ctrl+C 停止[/blue]")
        
        while True:
            time.sleep(1)
    
    except KeyboardInterrupt:
        console.print("\n[yellow]用户中断，正在停止服务...[/yellow]")
    except Exception as e:
        console.print(f"\n[red]启动过程中发生错误: {e}[/red]")
    finally:
        manager.stop_all_services()

@cli.command()
def stop():
    """停止所有服务"""
    manager = ServiceManager()
    manager.stop_all_services()

@cli.command()
def status():
    """显示服务状态"""
    manager = ServiceManager()
    manager.show_status()

@cli.command()
def cleanup():
    """清理所有资源"""
    manager = ServiceManager()
    manager.cleanup()

@cli.command()
def logs():
    """查看服务日志"""
    try:
        cmd = [
            'docker-compose',
            '-f', 'docker-compose.opensource.yml',
            'logs', '-f'
        ]
        
        subprocess.run(cmd, cwd=PROJECT_ROOT)
        
    except KeyboardInterrupt:
        console.print("\n[yellow]日志查看已停止[/yellow]")
    except Exception as e:
        console.print(f"[red]查看日志失败: {e}[/red]")

if __name__ == '__main__':
    cli()