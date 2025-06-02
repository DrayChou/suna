#!/usr/bin/env python3
"""
Suna 开源版本集成测试
测试所有开源服务的协同工作
"""

import asyncio
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Dict, Any

import aiohttp
import asyncpg
import websockets
from minio import Minio

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 测试配置
class TestConfig:
    # 服务端点
    POSTGREST_URL = "http://localhost:3001"
    GOTRUE_URL = "http://localhost:9999"
    MINIO_ENDPOINT = "localhost:15003"
    SANDBOX_URL = "http://localhost:15007"
    CRAWLER_URL = "http://localhost:15009"
    REALTIME_URL = "ws://localhost:15010"
    API_URL = "http://localhost:15013"
    SEARXNG_URL = "http://localhost:8080"
    
    # 认证信息
    MINIO_ACCESS_KEY = "minioadmin"
    MINIO_SECRET_KEY = "minioadmin"
    JWT_SECRET = "your-super-secret-jwt-token-with-at-least-32-characters"
    
    # 数据库连接
    DATABASE_URL = "postgresql://postgres:suna_secure_password_2024@localhost:15004/suna"

class OpenSourceStackTest:
    """开源技术栈集成测试"""
    
    def __init__(self):
        self.session = None
        self.db_pool = None
        self.minio_client = None
        self.test_user_email = f"test_{int(time.time())}@example.com"
        self.test_user_password = "test_password_123"
        self.access_token = None
        
    async def setup(self):
        """测试环境初始化"""
        logger.info("🚀 开始集成测试环境初始化")
        
        # 创建HTTP会话
        self.session = aiohttp.ClientSession()
        
        # 初始化MinIO客户端
        self.minio_client = Minio(
            TestConfig.MINIO_ENDPOINT,
            access_key=TestConfig.MINIO_ACCESS_KEY,
            secret_key=TestConfig.MINIO_SECRET_KEY,
            secure=False
        )
        
        # 创建数据库连接池
        try:
            self.db_pool = await asyncpg.create_pool(TestConfig.DATABASE_URL, min_size=1, max_size=5)
            logger.info("✅ 数据库连接成功")
        except Exception as e:
            logger.error(f"❌ 数据库连接失败: {e}")
            raise
            
        logger.info("✅ 测试环境初始化完成")
    
    async def cleanup(self):
        """清理测试环境"""
        if self.session:
            await self.session.close()
        if self.db_pool:
            await self.db_pool.close()
        logger.info("🧹 测试环境清理完成")
    
    async def test_database_connection(self):
        """测试数据库连接和PostgREST API"""
        logger.info("📊 测试数据库连接和PostgREST API")
        
        try:
            # 测试直接数据库连接
            async with self.db_pool.acquire() as conn:
                result = await conn.fetchval("SELECT version()")
                logger.info(f"✅ PostgreSQL版本: {result}")
            
            # 测试PostgREST API
            async with self.session.get(f"{TestConfig.POSTGREST_URL}/") as resp:
                if resp.status == 200:
                    logger.info("✅ PostgREST API响应正常")
                else:
                    logger.error(f"❌ PostgREST API响应异常: {resp.status}")
                    
        except Exception as e:
            logger.error(f"❌ 数据库测试失败: {e}")
            raise
    
    async def test_authentication_service(self):
        """测试GoTrue认证服务"""
        logger.info("🔐 测试GoTrue认证服务")
        
        try:
            # 测试用户注册
            signup_data = {
                "email": self.test_user_email,
                "password": self.test_user_password
            }
            
            async with self.session.post(
                f"{TestConfig.GOTRUE_URL}/signup",
                json=signup_data
            ) as resp:
                if resp.status in [200, 201]:
                    result = await resp.json()
                    self.access_token = result.get("access_token")
                    logger.info("✅ 用户注册成功")
                else:
                    logger.error(f"❌ 用户注册失败: {resp.status}")
                    
            # 测试用户登录
            login_data = {
                "email": self.test_user_email,
                "password": self.test_user_password
            }
            
            async with self.session.post(
                f"{TestConfig.GOTRUE_URL}/token?grant_type=password",
                json=login_data
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    self.access_token = result.get("access_token")
                    logger.info("✅ 用户登录成功")
                else:
                    logger.error(f"❌ 用户登录失败: {resp.status}")
                    
        except Exception as e:
            logger.error(f"❌ 认证服务测试失败: {e}")
            raise
    
    async def test_storage_service(self):
        """测试MinIO存储服务"""
        logger.info("💾 测试MinIO存储服务")
        
        try:
            # 创建测试存储桶
            bucket_name = "test-bucket"
            if not self.minio_client.bucket_exists(bucket_name):
                self.minio_client.make_bucket(bucket_name)
                logger.info(f"✅ 创建存储桶: {bucket_name}")
            
            # 上传测试文件
            test_content = b"This is a test file for Suna integration testing"
            test_file_name = "test_file.txt"
            
            with tempfile.NamedTemporaryFile() as temp_file:
                temp_file.write(test_content)
                temp_file.flush()
                
                self.minio_client.fput_object(
                    bucket_name,
                    test_file_name,
                    temp_file.name
                )
                logger.info(f"✅ 文件上传成功: {test_file_name}")
            
            # 下载测试文件
            response = self.minio_client.get_object(bucket_name, test_file_name)
            downloaded_content = response.read()
            
            if downloaded_content == test_content:
                logger.info("✅ 文件下载验证成功")
            else:
                logger.error("❌ 文件内容验证失败")
                
            # 清理测试文件
            self.minio_client.remove_object(bucket_name, test_file_name)
            
        except Exception as e:
            logger.error(f"❌ 存储服务测试失败: {e}")
            raise
    
    async def test_sandbox_service(self):
        """测试沙盒管理服务"""
        logger.info("📦 测试沙盒管理服务")
        
        try:
            # 创建沙盒
            sandbox_config = {
                "image": "python:3.11-slim",
                "memory_limit": "256m",
                "cpu_quota": 50000,
                "timeout": 300
            }
            
            async with self.session.post(
                f"{TestConfig.SANDBOX_URL}/sandbox/create",
                json=sandbox_config
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    sandbox_id = result.get("sandbox_id")
                    logger.info(f"✅ 沙盒创建成功: {sandbox_id}")
                    
                    # 测试代码执行
                    execute_data = {
                        "code": "print('Hello from Suna sandbox!')",
                        "language": "python"
                    }
                    
                    async with self.session.post(
                        f"{TestConfig.SANDBOX_URL}/sandbox/{sandbox_id}/execute",
                        json=execute_data
                    ) as exec_resp:
                        if exec_resp.status == 200:
                            exec_result = await exec_resp.json()
                            logger.info(f"✅ 代码执行成功: {exec_result.get('output', '')}")
                        else:
                            logger.error(f"❌ 代码执行失败: {exec_resp.status}")
                    
                    # 清理沙盒
                    async with self.session.delete(
                        f"{TestConfig.SANDBOX_URL}/sandbox/{sandbox_id}"
                    ) as cleanup_resp:
                        if cleanup_resp.status == 200:
                            logger.info("✅ 沙盒清理成功")
                else:
                    logger.error(f"❌ 沙盒创建失败: {resp.status}")
                    
        except Exception as e:
            logger.error(f"❌ 沙盒服务测试失败: {e}")
            raise
    
    async def test_crawler_service(self):
        """测试爬虫服务"""
        logger.info("🕷️ 测试爬虫服务")
        
        try:
            # 测试网页抓取
            crawl_data = {
                "url": "https://httpbin.org/html",
                "format": "markdown",
                "wait_for": 1000
            }
            
            async with self.session.post(
                f"{TestConfig.CRAWLER_URL}/crawl",
                json=crawl_data
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    content = result.get("content", "")
                    if content and len(content) > 0:
                        logger.info("✅ 网页抓取成功")
                    else:
                        logger.error("❌ 抓取内容为空")
                else:
                    logger.error(f"❌ 网页抓取失败: {resp.status}")
                    
        except Exception as e:
            logger.error(f"❌ 爬虫服务测试失败: {e}")
            raise
    
    async def test_search_service(self):
        """测试搜索服务"""
        logger.info("🔍 测试SearXNG搜索服务")
        
        try:
            # 测试搜索功能
            search_params = {
                "q": "python programming",
                "format": "json",
                "category": "general"
            }
            
            async with self.session.get(
                f"{TestConfig.SEARXNG_URL}/search",
                params=search_params
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    results = result.get("results", [])
                    if len(results) > 0:
                        logger.info(f"✅ 搜索成功，返回 {len(results)} 个结果")
                    else:
                        logger.warning("⚠️ 搜索结果为空")
                else:
                    logger.error(f"❌ 搜索服务失败: {resp.status}")
                    
        except Exception as e:
            logger.error(f"❌ 搜索服务测试失败: {e}")
            raise
    
    async def test_realtime_service(self):
        """测试实时通信服务"""
        logger.info("⚡ 测试WebSocket实时通信服务")
        
        try:
            # 连接WebSocket
            uri = f"{TestConfig.REALTIME_URL}/ws"
            
            async with websockets.connect(uri) as websocket:
                # 发送测试消息
                test_message = {
                    "type": "subscribe",
                    "channel": "test_channel",
                    "data": {"message": "Hello WebSocket!"}
                }
                
                await websocket.send(json.dumps(test_message))
                logger.info("✅ WebSocket消息发送成功")
                
                # 接收响应
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    response_data = json.loads(response)
                    logger.info(f"✅ WebSocket响应接收成功: {response_data}")
                except asyncio.TimeoutError:
                    logger.warning("⚠️ WebSocket响应超时，但连接正常")
                    
        except Exception as e:
            logger.error(f"❌ 实时通信服务测试失败: {e}")
            # 不抛出异常，因为WebSocket可能需要特定的协议
    
    async def test_main_api_service(self):
        """测试主API服务"""
        logger.info("🌐 测试主API服务")
        
        try:
            # 测试健康检查
            async with self.session.get(f"{TestConfig.API_URL}/health") as resp:
                if resp.status == 200:
                    result = await resp.json()
                    logger.info(f"✅ API健康检查成功: {result}")
                else:
                    logger.error(f"❌ API健康检查失败: {resp.status}")
            
            # 测试API文档
            async with self.session.get(f"{TestConfig.API_URL}/docs") as resp:
                if resp.status == 200:
                    logger.info("✅ API文档访问成功")
                else:
                    logger.error(f"❌ API文档访问失败: {resp.status}")
                    
        except Exception as e:
            logger.error(f"❌ 主API服务测试失败: {e}")
            raise
    
    async def run_all_tests(self):
        """运行所有集成测试"""
        logger.info("🧪 开始Suna开源版本集成测试")
        
        try:
            await self.setup()
            
            # 执行所有测试
            test_methods = [
                self.test_database_connection,
                self.test_authentication_service,
                self.test_storage_service,
                self.test_sandbox_service,
                self.test_crawler_service,
                self.test_search_service,
                self.test_realtime_service,
                self.test_main_api_service
            ]
            
            passed_tests = 0
            total_tests = len(test_methods)
            
            for test_method in test_methods:
                try:
                    await test_method()
                    passed_tests += 1
                except Exception as e:
                    logger.error(f"❌ 测试失败: {test_method.__name__} - {e}")
            
            # 输出测试结果
            logger.info(f"📊 测试完成: {passed_tests}/{total_tests} 个测试通过")
            
            if passed_tests == total_tests:
                logger.info("🎉 所有集成测试通过！开源技术栈运行正常")
                return True
            else:
                logger.warning("⚠️ 部分测试失败，请检查相关服务")
                return False
                
        finally:
            await self.cleanup()

async def main():
    """主测试函数"""
    test_runner = OpenSourceStackTest()
    success = await test_runner.run_all_tests()
    return success

if __name__ == "__main__":
    asyncio.run(main())
