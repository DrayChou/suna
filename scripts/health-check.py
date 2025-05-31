#!/usr/bin/env python3
"""
Suna 开源版本健康检查脚本
用于检查所有服务的健康状态
"""

import asyncio
import json
import socket
import sys
import time
from typing import Dict, List, Tuple

import aiohttp
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

class HealthChecker:
    """健康检查器"""
    
    def __init__(self):
        self.services = {
            'PostgreSQL': {
                'type': 'tcp',
                'host': 'localhost',
                'port': 5432,
                'timeout': 5
            },
            'PostgREST': {
                'type': 'http',
                'url': 'http://localhost:3001/',
                'timeout': 10
            },
            'GoTrue': {
                'type': 'http',
                'url': 'http://localhost:9999/health',
                'timeout': 10
            },
            'MinIO': {
                'type': 'http',
                'url': 'http://localhost:9000/minio/health/live',
                'timeout': 10
            },
            'Redis': {
                'type': 'tcp',
                'host': 'localhost',
                'port': 6379,
                'timeout': 5
            },
            'RabbitMQ': {
                'type': 'http',
                'url': 'http://localhost:15672/api/overview',
                'timeout': 10,
                'auth': ('guest', 'guest')
            },
            'API服务': {
                'type': 'http',
                'url': 'http://localhost:8000/health',
                'timeout': 10
            },
            '沙盒管理': {
                'type': 'http',
                'url': 'http://localhost:8001/health',
                'timeout': 10
            },
            '爬虫服务': {
                'type': 'http',
                'url': 'http://localhost:8002/health',
                'timeout': 10
            },
            '实时通信': {
                'type': 'http',
                'url': 'http://localhost:8003/health',
                'timeout': 10
            },
            'SearXNG': {
                'type': 'http',
                'url': 'http://localhost:8080/',
                'timeout': 10
            },
            'Prometheus': {
                'type': 'http',
                'url': 'http://localhost:9090/-/healthy',
                'timeout': 10
            },
            'Grafana': {
                'type': 'http',
                'url': 'http://localhost:3000/api/health',
                'timeout': 10
            }
        }
    
    def check_tcp_port(self, host: str, port: int, timeout: int = 5) -> Tuple[bool, str]:
        """检查TCP端口连通性"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                return True, "连接成功"
            else:
                return False, f"连接失败 (错误码: {result})"
                
        except Exception as e:
            return False, f"连接异常: {str(e)}"
    
    async def check_http_endpoint(self, url: str, timeout: int = 10, auth: Tuple[str, str] = None) -> Tuple[bool, str]:
        """检查HTTP端点健康状态"""
        try:
            auth_obj = aiohttp.BasicAuth(auth[0], auth[1]) if auth else None
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                async with session.get(url, auth=auth_obj) as response:
                    if response.status < 400:
                        return True, f"HTTP {response.status}"
                    else:
                        return False, f"HTTP {response.status}"
                        
        except aiohttp.ClientTimeout:
            return False, "请求超时"
        except aiohttp.ClientError as e:
            return False, f"连接错误: {str(e)}"
        except Exception as e:
            return False, f"未知错误: {str(e)}"
    
    async def check_service(self, name: str, config: Dict) -> Tuple[str, bool, str, float]:
        """检查单个服务"""
        start_time = time.time()
        
        try:
            if config['type'] == 'tcp':
                success, message = self.check_tcp_port(
                    config['host'], 
                    config['port'], 
                    config.get('timeout', 5)
                )
            elif config['type'] == 'http':
                success, message = await self.check_http_endpoint(
                    config['url'],
                    config.get('timeout', 10),
                    config.get('auth')
                )
            else:
                success, message = False, "未知的检查类型"
                
        except Exception as e:
            success, message = False, f"检查异常: {str(e)}"
        
        response_time = (time.time() - start_time) * 1000  # 转换为毫秒
        
        return name, success, message, response_time
    
    async def check_all_services(self) -> List[Tuple[str, bool, str, float]]:
        """检查所有服务"""
        tasks = []
        
        for name, config in self.services.items():
            task = self.check_service(name, config)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                service_name = list(self.services.keys())[i]
                processed_results.append((service_name, False, f"检查异常: {str(result)}", 0.0))
            else:
                processed_results.append(result)
        
        return processed_results
    
    def display_results(self, results: List[Tuple[str, bool, str, float]], show_details: bool = True):
        """显示检查结果"""
        table = Table(title="Suna 服务健康检查报告")
        table.add_column("服务名称", style="cyan", width=15)
        table.add_column("状态", style="bold", width=8)
        table.add_column("响应时间", style="yellow", width=10)
        
        if show_details:
            table.add_column("详细信息", style="dim", width=30)
        
        healthy_count = 0
        total_count = len(results)
        
        for name, is_healthy, message, response_time in results:
            if is_healthy:
                status = "[green]✓ 健康[/green]"
                healthy_count += 1
            else:
                status = "[red]✗ 异常[/red]"
            
            response_time_str = f"{response_time:.1f}ms" if response_time > 0 else "N/A"
            
            if show_details:
                table.add_row(name, status, response_time_str, message)
            else:
                table.add_row(name, status, response_time_str)
        
        console.print(table)
        
        # 显示总结
        if healthy_count == total_count:
            summary_color = "green"
            summary_icon = "✓"
            summary_text = "所有服务运行正常"
        elif healthy_count > 0:
            summary_color = "yellow"
            summary_icon = "⚠"
            summary_text = f"{healthy_count}/{total_count} 服务正常运行"
        else:
            summary_color = "red"
            summary_icon = "✗"
            summary_text = "所有服务都存在问题"
        
        console.print(f"\n[{summary_color}]{summary_icon} {summary_text}[/{summary_color}]")
        
        return healthy_count == total_count
    
    def generate_report(self, results: List[Tuple[str, bool, str, float]]) -> Dict:
        """生成详细报告"""
        report = {
            'timestamp': time.time(),
            'total_services': len(results),
            'healthy_services': sum(1 for _, is_healthy, _, _ in results if is_healthy),
            'services': []
        }
        
        for name, is_healthy, message, response_time in results:
            service_report = {
                'name': name,
                'healthy': is_healthy,
                'message': message,
                'response_time_ms': response_time
            }
            report['services'].append(service_report)
        
        return report

@click.group()
def cli():
    """Suna 健康检查工具"""
    pass

@cli.command()
@click.option('--details/--no-details', default=True, help='显示详细信息')
@click.option('--json-output', is_flag=True, help='以JSON格式输出')
@click.option('--output-file', help='输出文件路径')
async def check(details, json_output, output_file):
    """检查所有服务健康状态"""
    checker = HealthChecker()
    
    if not json_output:
        console.print(Panel.fit(
            "[bold blue]Suna 服务健康检查[/bold blue]\n\n"
            "正在检查所有服务的健康状态...",
            title="健康检查"
        ))
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console if not json_output else None
    ) as progress:
        task = progress.add_task("检查服务健康状态...", total=None)
        results = await checker.check_all_services()
        progress.update(task, description="检查完成")
    
    if json_output:
        report = checker.generate_report(results)
        output = json.dumps(report, indent=2, ensure_ascii=False)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(output)
            console.print(f"报告已保存到: {output_file}")
        else:
            print(output)
    else:
        all_healthy = checker.display_results(results, details)
        
        if output_file:
            report = checker.generate_report(results)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            console.print(f"\n详细报告已保存到: {output_file}")
        
        # 设置退出码
        if not all_healthy:
            sys.exit(1)

@cli.command()
@click.option('--interval', default=30, help='检查间隔（秒）')
@click.option('--max-failures', default=3, help='最大失败次数')
async def monitor(interval, max_failures):
    """持续监控服务健康状态"""
    checker = HealthChecker()
    failure_counts = {}
    
    console.print(Panel.fit(
        f"[bold blue]Suna 服务监控[/bold blue]\n\n"
        f"检查间隔: {interval}秒\n"
        f"最大失败次数: {max_failures}",
        title="服务监控"
    ))
    
    try:
        while True:
            console.print(f"\n[blue]检查时间: {time.strftime('%Y-%m-%d %H:%M:%S')}[/blue]")
            
            results = await checker.check_all_services()
            all_healthy = checker.display_results(results, False)
            
            # 检查失败计数
            for name, is_healthy, message, _ in results:
                if not is_healthy:
                    failure_counts[name] = failure_counts.get(name, 0) + 1
                    if failure_counts[name] >= max_failures:
                        console.print(f"[red]警告: {name} 连续失败 {failure_counts[name]} 次![/red]")
                else:
                    failure_counts[name] = 0
            
            await asyncio.sleep(interval)
            
    except KeyboardInterrupt:
        console.print("\n[yellow]监控已停止[/yellow]")

@cli.command()
@click.argument('service_name')
async def check_service(service_name):
    """检查单个服务"""
    checker = HealthChecker()
    
    if service_name not in checker.services:
        console.print(f"[red]错误: 未找到服务 '{service_name}'[/red]")
        console.print("可用服务:")
        for name in checker.services.keys():
            console.print(f"  - {name}")
        sys.exit(1)
    
    console.print(f"检查服务: {service_name}")
    
    name, is_healthy, message, response_time = await checker.check_service(
        service_name, 
        checker.services[service_name]
    )
    
    status = "[green]健康[/green]" if is_healthy else "[red]异常[/red]"
    response_time_str = f"{response_time:.1f}ms" if response_time > 0 else "N/A"
    
    console.print(f"状态: {status}")
    console.print(f"响应时间: {response_time_str}")
    console.print(f"详细信息: {message}")
    
    if not is_healthy:
        sys.exit(1)

def main():
    """主函数"""
    # 检查是否有异步命令
    if len(sys.argv) > 1 and sys.argv[1] in ['check', 'monitor', 'check-service']:
        # 运行异步命令
        import asyncio
        asyncio.run(cli())
    else:
        # 运行同步命令
        cli()

if __name__ == '__main__':
    main()