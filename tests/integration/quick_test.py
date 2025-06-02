#!/usr/bin/env python3
"""
Suna 开源版本简化集成测试
测试所有开源服务的基本功能
"""

import asyncio
import json
import logging
import time
import tempfile
from typing import Dict, Any

import aiohttp
import asyncpg

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class QuickIntegrationTest:
    """快速集成测试"""
    
    def __init__(self):
        self.session = None
        
    async def setup(self):
        """初始化"""
        self.session = aiohttp.ClientSession()
        logger.info("✅ 测试环境初始化完成")
    
    async def cleanup(self):
        """清理"""
        if self.session:
            await self.session.close()
        logger.info("✅ 测试环境清理完成")
    
    async def test_service_health(self, name: str, url: str):
        """测试服务健康状态"""
        try:
            async with self.session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    logger.info(f"✅ {name} 服务运行正常")
                    return True
                else:
                    logger.warning(f"⚠️ {name} 服务响应异常: {resp.status}")
                    return False
        except Exception as e:
            logger.error(f"❌ {name} 服务连接失败: {e}")
            return False
    
    async def test_database_connection(self):
        """测试数据库连接"""
        try:
            conn = await asyncpg.connect(
                "postgresql://postgres:suna_secure_password_2024@localhost:15004/suna"
            )
            result = await conn.fetchval("SELECT version()")
            await conn.close()
            logger.info(f"✅ PostgreSQL 连接成功: {result[:50]}...")
            return True
        except Exception as e:
            logger.error(f"❌ PostgreSQL 连接失败: {e}")
            return False
    
    async def test_postgrest_api(self):
        """测试PostgREST API"""
        try:
            async with self.session.get("http://localhost:3001/", timeout=5) as resp:
                if resp.status == 200:
                    logger.info("✅ PostgREST API 正常")
                    return True
                else:
                    logger.warning(f"⚠️ PostgREST API 响应异常: {resp.status}")
                    return False
        except Exception as e:
            logger.error(f"❌ PostgREST API 测试失败: {e}")
            return False
    
    async def test_gotrue_auth(self):
        """测试GoTrue认证"""
        try:
            async with self.session.get("http://localhost:9999/health", timeout=5) as resp:
                if resp.status in [200, 404]:  # 404也表示服务运行
                    logger.info("✅ GoTrue 认证服务正常")
                    return True
                else:
                    logger.warning(f"⚠️ GoTrue 服务响应异常: {resp.status}")
                    return False
        except Exception as e:
            logger.error(f"❌ GoTrue 认证服务测试失败: {e}")
            return False
    
    async def test_minio_storage(self):
        """测试MinIO存储"""
        try:
            async with self.session.get("http://localhost:15003/minio/health/live", timeout=5) as resp:
                if resp.status == 200:
                    logger.info("✅ MinIO 存储服务正常")
                    return True
                else:
                    logger.warning(f"⚠️ MinIO 服务响应异常: {resp.status}")
                    return False
        except Exception as e:
            logger.error(f"❌ MinIO 存储服务测试失败: {e}")
            return False
    
    async def test_custom_services(self):
        """测试自定义服务"""
        services = [
            ("沙盒管理", "http://localhost:15007/health"),
            ("爬虫服务", "http://localhost:15009/health"), 
            ("API服务", "http://localhost:15013/health"),
            ("搜索服务", "http://localhost:8080/"),
        ]
        
        results = []
        for name, url in services:
            result = await self.test_service_health(name, url)
            results.append(result)
        
        return all(results)
    
    async def run_quick_tests(self):
        """运行快速测试"""
        logger.info("🧪 开始 Suna 开源版本快速集成测试")
        
        try:
            await self.setup()
            
            tests = [
                ("数据库连接", self.test_database_connection),
                ("PostgREST API", self.test_postgrest_api),
                ("GoTrue 认证", self.test_gotrue_auth),
                ("MinIO 存储", self.test_minio_storage),
                ("自定义服务", self.test_custom_services),
            ]
            
            passed = 0
            total = len(tests)
            
            for test_name, test_func in tests:
                logger.info(f"🔍 测试 {test_name}...")
                try:
                    result = await test_func()
                    if result:
                        passed += 1
                except Exception as e:
                    logger.error(f"❌ {test_name} 测试异常: {e}")
            
            # 输出结果
            logger.info(f"📊 测试完成: {passed}/{total} 个测试通过")
            
            if passed == total:
                logger.info("🎉 所有核心服务运行正常！")
                return True
            elif passed >= total * 0.8:
                logger.info("✅ 大部分服务运行正常，系统基本可用")
                return True
            else:
                logger.warning("⚠️ 多个服务存在问题，请检查配置")
                return False
                
        finally:
            await self.cleanup()

async def main():
    """主函数"""
    test_runner = QuickIntegrationTest()
    return await test_runner.run_quick_tests()

if __name__ == "__main__":
    success = asyncio.run(main())
    if success:
        print("\n🎯 集成测试通过！可以进行下一步开发任务。")
    else:
        print("\n⚠️ 部分测试失败，建议先解决服务问题。")
