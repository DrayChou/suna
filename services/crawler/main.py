#!/usr/bin/env python3
"""
Suna 爬虫服务
替代 Firecrawl 的网页抓取功能，提供高性能的网页内容提取

主要功能：
- 网页内容抓取和解析
- JavaScript 渲染支持
- 多种输出格式（HTML、Markdown、文本）
- 反爬虫机制处理
- 批量抓取支持
- 内容清理和提取
- 截图功能
"""

import asyncio
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from urllib.parse import urljoin, urlparse

import aiofiles
import aiohttp
from bs4 import BeautifulSoup, Comment
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from markdownify import markdownify as md
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from pydantic import BaseModel, Field, HttpUrl
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
    HOST = os.getenv('CRAWLER_HOST', '0.0.0.0')
    PORT = int(os.getenv('CRAWLER_PORT', 8002))
    
    # 爬虫配置
    MAX_CONCURRENT_CRAWLS = int(os.getenv('MAX_CONCURRENT_CRAWLS', 5))
    CRAWL_TIMEOUT = int(os.getenv('CRAWL_TIMEOUT', 30))
    USER_AGENT = os.getenv('CRAWLER_USER_AGENT', 'Suna-Crawler/1.0 (+https://github.com/sunaai/suna)')
    
    # 浏览器配置
    HEADLESS = os.getenv('CRAWLER_HEADLESS', 'true').lower() == 'true'
    VIEWPORT_WIDTH = int(os.getenv('CRAWLER_VIEWPORT_WIDTH', 1920))
    VIEWPORT_HEIGHT = int(os.getenv('CRAWLER_VIEWPORT_HEIGHT', 1080))
    
    # 安全配置
    ALLOWED_ORIGINS = os.getenv('CORS_ORIGINS', 'http://localhost:3000,http://localhost:8000').split(',')
    MAX_CONTENT_SIZE = int(os.getenv('MAX_CONTENT_SIZE', 10 * 1024 * 1024))  # 10MB
    
    # 存储配置
    SCREENSHOTS_DIR = Path(os.getenv('SCREENSHOTS_DIR', '/tmp/suna_screenshots'))
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    
    # 反爬虫配置
    ENABLE_STEALTH = os.getenv('ENABLE_STEALTH', 'true').lower() == 'true'
    RANDOM_DELAY_MIN = float(os.getenv('RANDOM_DELAY_MIN', 1.0))
    RANDOM_DELAY_MAX = float(os.getenv('RANDOM_DELAY_MAX', 3.0))

# Pydantic 模型
class CrawlRequest(BaseModel):
    """爬取请求"""
    url: HttpUrl = Field(..., description="要爬取的URL")
    format: str = Field(default="markdown", description="输出格式: html, markdown, text, json")
    wait_for: Optional[str] = Field(default=None, description="等待的CSS选择器或时间（毫秒）")
    screenshot: bool = Field(default=False, description="是否截图")
    full_page_screenshot: bool = Field(default=False, description="是否全页截图")
    remove_selectors: Optional[List[str]] = Field(default=None, description="要移除的CSS选择器")
    only_selectors: Optional[List[str]] = Field(default=None, description="只保留的CSS选择器")
    headers: Optional[Dict[str, str]] = Field(default=None, description="自定义请求头")
    cookies: Optional[List[Dict[str, str]]] = Field(default=None, description="自定义Cookie")
    javascript: bool = Field(default=True, description="是否启用JavaScript")
    timeout: Optional[int] = Field(default=None, description="超时时间（秒）")
    user_agent: Optional[str] = Field(default=None, description="自定义User-Agent")
    proxy: Optional[str] = Field(default=None, description="代理服务器")
    extract_links: bool = Field(default=False, description="是否提取链接")
    extract_images: bool = Field(default=False, description="是否提取图片")
    extract_metadata: bool = Field(default=True, description="是否提取元数据")

class BatchCrawlRequest(BaseModel):
    """批量爬取请求"""
    urls: List[HttpUrl] = Field(..., description="要爬取的URL列表")
    format: str = Field(default="markdown", description="输出格式")
    concurrent_limit: Optional[int] = Field(default=None, description="并发限制")
    common_config: Optional[CrawlRequest] = Field(default=None, description="通用配置")

class CrawlResult(BaseModel):
    """爬取结果"""
    url: str
    title: Optional[str] = None
    content: str
    format: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    links: Optional[List[Dict[str, str]]] = None
    images: Optional[List[Dict[str, str]]] = None
    screenshot_url: Optional[str] = None
    crawl_time: float
    timestamp: datetime
    success: bool = True
    error: Optional[str] = None

class BatchCrawlResult(BaseModel):
    """批量爬取结果"""
    results: List[CrawlResult]
    total_urls: int
    successful_crawls: int
    failed_crawls: int
    total_time: float
    timestamp: datetime

# 内容提取器
class ContentExtractor:
    """内容提取器"""
    
    @staticmethod
    def clean_html(html: str, remove_selectors: List[str] = None) -> str:
        """清理HTML内容"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # 移除脚本和样式
        for script in soup(["script", "style", "noscript"]):
            script.decompose()
        
        # 移除注释
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
        
        # 移除指定的选择器
        if remove_selectors:
            for selector in remove_selectors:
                try:
                    for element in soup.select(selector):
                        element.decompose()
                except Exception as e:
                    logger.warning(f"移除选择器 {selector} 失败: {e}")
        
        # 移除空的标签
        for tag in soup.find_all():
            if not tag.get_text(strip=True) and not tag.find_all(['img', 'br', 'hr', 'input']):
                tag.decompose()
        
        return str(soup)
    
    @staticmethod
    def extract_main_content(soup: BeautifulSoup) -> BeautifulSoup:
        """提取主要内容"""
        # 尝试找到主要内容区域
        main_selectors = [
            'main', 'article', '[role="main"]',
            '.main-content', '.content', '.post-content',
            '#main', '#content', '#post-content',
            '.entry-content', '.article-content'
        ]
        
        for selector in main_selectors:
            main_content = soup.select_one(selector)
            if main_content and main_content.get_text(strip=True):
                return main_content
        
        # 如果没找到，返回body
        body = soup.find('body')
        return body if body else soup
    
    @staticmethod
    def html_to_markdown(html: str) -> str:
        """将HTML转换为Markdown"""
        try:
            # 配置markdownify
            markdown = md(
                html,
                heading_style="ATX",
                bullets="-",
                strip=['script', 'style'],
                convert=['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 
                        'strong', 'em', 'a', 'ul', 'ol', 'li', 
                        'blockquote', 'code', 'pre', 'img', 'br']
            )
            
            # 清理多余的空行
            markdown = re.sub(r'\n\s*\n\s*\n', '\n\n', markdown)
            markdown = markdown.strip()
            
            return markdown
        except Exception as e:
            logger.error(f"HTML转Markdown失败: {e}")
            return BeautifulSoup(html, 'html.parser').get_text()
    
    @staticmethod
    def html_to_text(html: str) -> str:
        """将HTML转换为纯文本"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # 在块级元素后添加换行
        for tag in soup.find_all(['p', 'div', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            tag.append('\n')
        
        text = soup.get_text()
        
        # 清理多余的空白
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        return text.strip()
    
    @staticmethod
    def extract_metadata(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """提取页面元数据"""
        metadata = {
            'url': url,
            'domain': urlparse(url).netloc
        }
        
        # 标题
        title_tag = soup.find('title')
        if title_tag:
            metadata['title'] = title_tag.get_text().strip()
        
        # Meta标签
        meta_tags = soup.find_all('meta')
        for meta in meta_tags:
            name = meta.get('name') or meta.get('property') or meta.get('http-equiv')
            content = meta.get('content')
            
            if name and content:
                name = name.lower().replace(':', '_')
                metadata[f'meta_{name}'] = content
        
        # 语言
        html_tag = soup.find('html')
        if html_tag and html_tag.get('lang'):
            metadata['language'] = html_tag.get('lang')
        
        # 字符集
        charset_meta = soup.find('meta', {'charset': True})
        if charset_meta:
            metadata['charset'] = charset_meta.get('charset')
        
        return metadata
    
    @staticmethod
    def extract_links(soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
        """提取链接"""
        links = []
        
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            text = link.get_text().strip()
            title = link.get('title', '')
            
            # 转换为绝对URL
            absolute_url = urljoin(base_url, href)
            
            links.append({
                'url': absolute_url,
                'text': text,
                'title': title,
                'original_href': href
            })
        
        return links
    
    @staticmethod
    def extract_images(soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
        """提取图片"""
        images = []
        
        for img in soup.find_all('img', src=True):
            src = img.get('src')
            alt = img.get('alt', '')
            title = img.get('title', '')
            
            # 转换为绝对URL
            absolute_url = urljoin(base_url, src)
            
            images.append({
                'url': absolute_url,
                'alt': alt,
                'title': title,
                'original_src': src
            })
        
        return images

# 爬虫管理器
class CrawlerManager:
    """爬虫管理器"""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.semaphore = asyncio.Semaphore(Config.MAX_CONCURRENT_CRAWLS)
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def initialize(self):
        """初始化浏览器和会话"""
        try:
            # 初始化Playwright
            self.playwright = await async_playwright().start()
            
            # 启动浏览器
            self.browser = await self.playwright.chromium.launch(
                headless=Config.HEADLESS,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-default-apps',
                    '--disable-extensions'
                ]
            )
            
            # 创建浏览器上下文
            self.context = await self.browser.new_context(
                viewport={'width': Config.VIEWPORT_WIDTH, 'height': Config.VIEWPORT_HEIGHT},
                user_agent=Config.USER_AGENT
            )
            
            # 如果启用隐身模式
            if Config.ENABLE_STEALTH:
                await self.context.add_init_script("""
                    // 隐藏webdriver属性
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined,
                    });
                    
                    // 修改plugins长度
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5],
                    });
                    
                    // 修改语言
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en'],
                    });
                """)
            
            # 初始化HTTP会话
            timeout = aiohttp.ClientTimeout(total=Config.CRAWL_TIMEOUT)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={'User-Agent': Config.USER_AGENT}
            )
            
            logger.info("爬虫管理器初始化完成")
            
        except Exception as e:
            logger.error(f"初始化爬虫管理器失败: {e}")
            raise
    
    async def crawl_url(self, request: CrawlRequest) -> CrawlResult:
        """爬取单个URL"""
        start_time = time.time()
        url = str(request.url)
        
        async with self.semaphore:
            try:
                logger.info(f"开始爬取: {url}")
                
                # 根据是否需要JavaScript选择爬取方式
                if request.javascript:
                    result = await self._crawl_with_browser(request)
                else:
                    result = await self._crawl_with_http(request)
                
                result.crawl_time = time.time() - start_time
                result.timestamp = datetime.now()
                result.success = True
                
                logger.info(f"爬取完成: {url}, 耗时: {result.crawl_time:.2f}s")
                return result
                
            except Exception as e:
                logger.error(f"爬取失败: {url}, 错误: {e}")
                
                return CrawlResult(
                    url=url,
                    content="",
                    format=request.format,
                    crawl_time=time.time() - start_time,
                    timestamp=datetime.now(),
                    success=False,
                    error=str(e)
                )
    
    async def _crawl_with_browser(self, request: CrawlRequest) -> CrawlResult:
        """使用浏览器爬取（支持JavaScript）"""
        url = str(request.url)
        page = await self.context.new_page()
        
        try:
            # 设置自定义请求头
            if request.headers:
                await page.set_extra_http_headers(request.headers)
            
            # 设置Cookie
            if request.cookies:
                await page.context.add_cookies(request.cookies)
            
            # 设置User-Agent
            if request.user_agent:
                await page.set_user_agent(request.user_agent)
            
            # 导航到页面
            timeout = (request.timeout or Config.CRAWL_TIMEOUT) * 1000
            await page.goto(url, timeout=timeout, wait_until='domcontentloaded')
            
            # 等待指定条件
            if request.wait_for:
                if request.wait_for.isdigit():
                    # 等待指定时间
                    await page.wait_for_timeout(int(request.wait_for))
                else:
                    # 等待CSS选择器
                    try:
                        await page.wait_for_selector(request.wait_for, timeout=timeout)
                    except Exception as e:
                        logger.warning(f"等待选择器 {request.wait_for} 超时: {e}")
            
            # 随机延迟（反爬虫）
            if Config.ENABLE_STEALTH:
                import random
                delay = random.uniform(Config.RANDOM_DELAY_MIN, Config.RANDOM_DELAY_MAX)
                await page.wait_for_timeout(int(delay * 1000))
            
            # 获取页面内容
            html = await page.content()
            
            # 截图
            screenshot_url = None
            if request.screenshot:
                screenshot_url = await self._take_screenshot(page, url, request.full_page_screenshot)
            
            # 处理内容
            result = await self._process_content(
                html, url, request.format,
                request.remove_selectors, request.only_selectors,
                request.extract_links, request.extract_images, request.extract_metadata
            )
            
            result.screenshot_url = screenshot_url
            return result
            
        finally:
            await page.close()
    
    async def _crawl_with_http(self, request: CrawlRequest) -> CrawlResult:
        """使用HTTP客户端爬取（不支持JavaScript）"""
        url = str(request.url)
        
        headers = {
            'User-Agent': request.user_agent or Config.USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        if request.headers:
            headers.update(request.headers)
        
        timeout = request.timeout or Config.CRAWL_TIMEOUT
        
        async with self.session.get(
            url, 
            headers=headers, 
            timeout=aiohttp.ClientTimeout(total=timeout),
            proxy=request.proxy
        ) as response:
            
            # 检查内容大小
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > Config.MAX_CONTENT_SIZE:
                raise HTTPException(status_code=413, detail="内容过大")
            
            html = await response.text()
            
            # 检查实际内容大小
            if len(html.encode('utf-8')) > Config.MAX_CONTENT_SIZE:
                raise HTTPException(status_code=413, detail="内容过大")
            
            return await self._process_content(
                html, url, request.format,
                request.remove_selectors, request.only_selectors,
                request.extract_links, request.extract_images, request.extract_metadata
            )
    
    async def _process_content(
        self, 
        html: str, 
        url: str, 
        format: str,
        remove_selectors: Optional[List[str]] = None,
        only_selectors: Optional[List[str]] = None,
        extract_links: bool = False,
        extract_images: bool = False,
        extract_metadata: bool = True
    ) -> CrawlResult:
        """处理页面内容"""
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # 提取元数据
        metadata = {}
        title = None
        if extract_metadata:
            metadata = ContentExtractor.extract_metadata(soup, url)
            title = metadata.get('title')
        
        # 只保留指定选择器的内容
        if only_selectors:
            new_soup = BeautifulSoup('<html><body></body></html>', 'html.parser')
            body = new_soup.find('body')
            
            for selector in only_selectors:
                try:
                    elements = soup.select(selector)
                    for element in elements:
                        body.append(element.extract())
                except Exception as e:
                    logger.warning(f"选择器 {selector} 处理失败: {e}")
            
            soup = new_soup
        
        # 清理HTML
        clean_html = ContentExtractor.clean_html(str(soup), remove_selectors)
        soup = BeautifulSoup(clean_html, 'html.parser')
        
        # 提取主要内容
        main_content = ContentExtractor.extract_main_content(soup)
        
        # 根据格式转换内容
        if format.lower() == 'html':
            content = str(main_content)
        elif format.lower() == 'markdown':
            content = ContentExtractor.html_to_markdown(str(main_content))
        elif format.lower() == 'text':
            content = ContentExtractor.html_to_text(str(main_content))
        elif format.lower() == 'json':
            content = json.dumps({
                'html': str(main_content),
                'text': ContentExtractor.html_to_text(str(main_content)),
                'markdown': ContentExtractor.html_to_markdown(str(main_content))
            }, ensure_ascii=False, indent=2)
        else:
            content = ContentExtractor.html_to_markdown(str(main_content))
        
        # 提取链接和图片
        links = None
        images = None
        
        if extract_links:
            links = ContentExtractor.extract_links(soup, url)
        
        if extract_images:
            images = ContentExtractor.extract_images(soup, url)
        
        return CrawlResult(
            url=url,
            title=title,
            content=content,
            format=format,
            metadata=metadata,
            links=links,
            images=images
        )
    
    async def _take_screenshot(self, page: Page, url: str, full_page: bool = False) -> str:
        """截图"""
        try:
            screenshot_id = str(uuid.uuid4())
            screenshot_path = Config.SCREENSHOTS_DIR / f"{screenshot_id}.png"
            
            await page.screenshot(
                path=str(screenshot_path),
                full_page=full_page
            )
            
            # 返回相对URL
            return f"/screenshots/{screenshot_id}.png"
            
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return None
    
    async def batch_crawl(self, request: BatchCrawlRequest) -> BatchCrawlResult:
        """批量爬取"""
        start_time = time.time()
        
        # 设置并发限制
        concurrent_limit = request.concurrent_limit or Config.MAX_CONCURRENT_CRAWLS
        semaphore = asyncio.Semaphore(concurrent_limit)
        
        async def crawl_single(url: HttpUrl) -> CrawlResult:
            async with semaphore:
                # 使用通用配置或默认配置
                if request.common_config:
                    crawl_request = request.common_config.copy()
                    crawl_request.url = url
                else:
                    crawl_request = CrawlRequest(url=url, format=request.format)
                
                return await self.crawl_url(crawl_request)
        
        # 并发执行爬取任务
        tasks = [crawl_single(url) for url in request.urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        crawl_results = []
        successful_crawls = 0
        failed_crawls = 0
        
        for result in results:
            if isinstance(result, Exception):
                failed_crawls += 1
                crawl_results.append(CrawlResult(
                    url="unknown",
                    content="",
                    format=request.format,
                    crawl_time=0,
                    timestamp=datetime.now(),
                    success=False,
                    error=str(result)
                ))
            else:
                if result.success:
                    successful_crawls += 1
                else:
                    failed_crawls += 1
                crawl_results.append(result)
        
        total_time = time.time() - start_time
        
        return BatchCrawlResult(
            results=crawl_results,
            total_urls=len(request.urls),
            successful_crawls=successful_crawls,
            failed_crawls=failed_crawls,
            total_time=total_time,
            timestamp=datetime.now()
        )
    
    async def cleanup(self):
        """清理资源"""
        try:
            if self.session:
                await self.session.close()
            
            if self.context:
                await self.context.close()
            
            if self.browser:
                await self.browser.close()
            
            if hasattr(self, 'playwright'):
                await self.playwright.stop()
            
            logger.info("爬虫管理器资源清理完成")
            
        except Exception as e:
            logger.error(f"清理爬虫管理器资源失败: {e}")

# 全局爬虫管理器实例
crawler_manager = CrawlerManager()

# FastAPI 应用
app = FastAPI(
    title="Suna 爬虫服务",
    description="提供高性能的网页内容抓取和解析",
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
@app.post("/crawl", response_model=CrawlResult)
async def crawl_single_url(request: CrawlRequest):
    """爬取单个URL"""
    return await crawler_manager.crawl_url(request)

@app.post("/crawl/batch", response_model=BatchCrawlResult)
async def crawl_multiple_urls(request: BatchCrawlRequest):
    """批量爬取URL"""
    return await crawler_manager.batch_crawl(request)

@app.get("/screenshots/{screenshot_id}")
async def get_screenshot(screenshot_id: str):
    """获取截图"""
    from fastapi.responses import FileResponse
    
    screenshot_path = Config.SCREENSHOTS_DIR / f"{screenshot_id}"
    
    if not screenshot_path.exists():
        raise HTTPException(status_code=404, detail="截图不存在")
    
    return FileResponse(
        path=str(screenshot_path),
        media_type="image/png",
        filename=f"{screenshot_id}"
    )

@app.get("/health")
async def health_check():
    """健康检查"""
    try:
        # 检查浏览器状态
        browser_status = "healthy" if crawler_manager.browser and crawler_manager.browser.is_connected() else "disconnected"
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "browser_status": browser_status,
            "max_concurrent_crawls": Config.MAX_CONCURRENT_CRAWLS
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"服务不健康: {str(e)}")

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化"""
    logger.info("正在启动爬虫服务...")
    await crawler_manager.initialize()
    logger.info("爬虫服务启动完成")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理资源"""
    logger.info("正在关闭爬虫服务...")
    await crawler_manager.cleanup()
    logger.info("爬虫服务已关闭")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=Config.HOST,
        port=Config.PORT,
        reload=True,
        log_level="info"
    )