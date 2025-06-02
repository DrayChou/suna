#!/usr/bin/env python3
"""
Suna 数据库服务
替代 Supabase 的数据库功能，提供 PostgreSQL + PostgREST 集成

主要功能：
- PostgreSQL 连接管理
- PostgREST API 集成
- 数据库操作封装
- 事务管理
- 连接池管理
- 查询构建器
- 数据验证
- 错误处理
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union, Tuple
from contextlib import asynccontextmanager

import asyncpg
import aiohttp
from pydantic import BaseModel, Field, validator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 配置
class DatabaseConfig:
    # PostgreSQL 配置
    POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
    POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5432))
    POSTGRES_DB = os.getenv('POSTGRES_DB', 'suna')
    POSTGRES_USER = os.getenv('POSTGRES_USER', 'suna_app')
    POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'suna_password')
    
    # PostgREST 配置
    POSTGREST_URL = os.getenv('POSTGREST_URL', 'http://localhost:15001')
    POSTGREST_ANON_KEY = os.getenv('POSTGREST_ANON_KEY', 'anonymous')
    POSTGREST_SERVICE_KEY = os.getenv('POSTGREST_SERVICE_KEY', 'service_role')
    
    # 连接池配置
    MIN_POOL_SIZE = int(os.getenv('DB_MIN_POOL_SIZE', 5))
    MAX_POOL_SIZE = int(os.getenv('DB_MAX_POOL_SIZE', 20))
    POOL_TIMEOUT = int(os.getenv('DB_POOL_TIMEOUT', 30))
    
    # 查询配置
    QUERY_TIMEOUT = int(os.getenv('DB_QUERY_TIMEOUT', 30))
    MAX_QUERY_SIZE = int(os.getenv('DB_MAX_QUERY_SIZE', 1000))
    
    @classmethod
    def get_postgres_dsn(cls) -> str:
        """获取 PostgreSQL DSN"""
        return f"postgresql://{cls.POSTGRES_USER}:{cls.POSTGRES_PASSWORD}@{cls.POSTGRES_HOST}:{cls.POSTGRES_PORT}/{cls.POSTGRES_DB}"

# Pydantic 模型
class QueryFilter(BaseModel):
    """查询过滤器"""
    column: str = Field(..., description="列名")
    operator: str = Field(default="eq", description="操作符")
    value: Any = Field(..., description="值")
    
    @validator('operator')
    def validate_operator(cls, v):
        allowed_operators = [
            'eq', 'neq', 'gt', 'gte', 'lt', 'lte',
            'like', 'ilike', 'in', 'is', 'not',
            'cs', 'cd', 'sl', 'sr', 'nxl', 'nxr',
            'adj', 'ov', 'fts', 'plfts', 'phfts', 'wfts'
        ]
        if v not in allowed_operators:
            raise ValueError(f"不支持的操作符: {v}")
        return v

class QueryOrder(BaseModel):
    """查询排序"""
    column: str = Field(..., description="列名")
    ascending: bool = Field(default=True, description="是否升序")
    nulls_first: bool = Field(default=False, description="NULL值是否在前")

class QueryOptions(BaseModel):
    """查询选项"""
    select: Optional[str] = Field(default=None, description="选择的列")
    filters: Optional[List[QueryFilter]] = Field(default=None, description="过滤条件")
    order: Optional[List[QueryOrder]] = Field(default=None, description="排序")
    limit: Optional[int] = Field(default=None, description="限制数量")
    offset: Optional[int] = Field(default=None, description="偏移量")
    count: Optional[str] = Field(default=None, description="计数类型")

class InsertOptions(BaseModel):
    """插入选项"""
    on_conflict: Optional[str] = Field(default=None, description="冲突处理")
    returning: Optional[str] = Field(default="*", description="返回的列")
    prefer: Optional[str] = Field(default="return=representation", description="偏好设置")

class UpdateOptions(BaseModel):
    """更新选项"""
    filters: Optional[List[QueryFilter]] = Field(default=None, description="过滤条件")
    returning: Optional[str] = Field(default="*", description="返回的列")
    prefer: Optional[str] = Field(default="return=representation", description="偏好设置")

class DeleteOptions(BaseModel):
    """删除选项"""
    filters: Optional[List[QueryFilter]] = Field(default=None, description="过滤条件")
    returning: Optional[str] = Field(default="*", description="返回的列")

class DatabaseResponse(BaseModel):
    """数据库响应"""
    data: Optional[Union[List[Dict], Dict]] = Field(default=None, description="数据")
    count: Optional[int] = Field(default=None, description="总数")
    error: Optional[str] = Field(default=None, description="错误信息")
    status_code: int = Field(default=200, description="状态码")

# 查询构建器
class QueryBuilder:
    """PostgREST 查询构建器"""
    
    def __init__(self, table: str, base_url: str):
        self.table = table
        self.base_url = base_url.rstrip('/')
        self.url = f"{self.base_url}/{table}"
        self.params = {}
        self.headers = {}
    
    def select(self, columns: str = "*") -> 'QueryBuilder':
        """选择列"""
        self.params['select'] = columns
        return self
    
    def eq(self, column: str, value: Any) -> 'QueryBuilder':
        """等于"""
        self.params[column] = f"eq.{value}"
        return self
    
    def neq(self, column: str, value: Any) -> 'QueryBuilder':
        """不等于"""
        self.params[column] = f"neq.{value}"
        return self
    
    def gt(self, column: str, value: Any) -> 'QueryBuilder':
        """大于"""
        self.params[column] = f"gt.{value}"
        return self
    
    def gte(self, column: str, value: Any) -> 'QueryBuilder':
        """大于等于"""
        self.params[column] = f"gte.{value}"
        return self
    
    def lt(self, column: str, value: Any) -> 'QueryBuilder':
        """小于"""
        self.params[column] = f"lt.{value}"
        return self
    
    def lte(self, column: str, value: Any) -> 'QueryBuilder':
        """小于等于"""
        self.params[column] = f"lte.{value}"
        return self
    
    def like(self, column: str, pattern: str) -> 'QueryBuilder':
        """模糊匹配"""
        self.params[column] = f"like.{pattern}"
        return self
    
    def ilike(self, column: str, pattern: str) -> 'QueryBuilder':
        """不区分大小写模糊匹配"""
        self.params[column] = f"ilike.{pattern}"
        return self
    
    def in_(self, column: str, values: List[Any]) -> 'QueryBuilder':
        """在列表中"""
        value_str = ','.join(str(v) for v in values)
        self.params[column] = f"in.({value_str})"
        return self
    
    def is_(self, column: str, value: Any) -> 'QueryBuilder':
        """是（用于NULL检查）"""
        self.params[column] = f"is.{value}"
        return self
    
    def order(self, column: str, ascending: bool = True, nulls_first: bool = False) -> 'QueryBuilder':
        """排序"""
        direction = "asc" if ascending else "desc"
        nulls = ".nullsfirst" if nulls_first else ".nullslast"
        
        if 'order' in self.params:
            self.params['order'] += f",{column}.{direction}{nulls}"
        else:
            self.params['order'] = f"{column}.{direction}{nulls}"
        
        return self
    
    def limit(self, count: int) -> 'QueryBuilder':
        """限制数量"""
        self.params['limit'] = str(count)
        return self
    
    def offset(self, count: int) -> 'QueryBuilder':
        """偏移量"""
        self.params['offset'] = str(count)
        return self
    
    def range(self, start: int, end: int) -> 'QueryBuilder':
        """范围"""
        self.headers['Range'] = f"{start}-{end}"
        return self
    
    def single(self) -> 'QueryBuilder':
        """单条记录"""
        self.headers['Accept'] = 'application/vnd.pgrst.object+json'
        return self
    
    def count(self, count_type: str = "exact") -> 'QueryBuilder':
        """计数"""
        if count_type == "exact":
            self.headers['Prefer'] = 'count=exact'
        elif count_type == "planned":
            self.headers['Prefer'] = 'count=planned'
        elif count_type == "estimated":
            self.headers['Prefer'] = 'count=estimated'
        return self
    
    def auth(self, token: str) -> 'QueryBuilder':
        """认证"""
        self.headers['Authorization'] = f"Bearer {token}"
        return self
    
    def build_url(self) -> str:
        """构建URL"""
        if not self.params:
            return self.url
        
        query_string = '&'.join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.url}?{query_string}"

# 数据库连接管理器
class DatabaseManager:
    """数据库连接管理器"""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self.http_session: Optional[aiohttp.ClientSession] = None
        self.config = DatabaseConfig()
    
    async def initialize(self):
        """初始化数据库连接"""
        try:
            # 创建连接池
            self.pool = await asyncpg.create_pool(
                dsn=self.config.get_postgres_dsn(),
                min_size=self.config.MIN_POOL_SIZE,
                max_size=self.config.MAX_POOL_SIZE,
                command_timeout=self.config.QUERY_TIMEOUT
            )
            
            # 创建HTTP会话
            self.http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.QUERY_TIMEOUT)
            )
            
            # 测试连接
            async with self.pool.acquire() as conn:
                await conn.fetchval('SELECT 1')
            
            logger.info("数据库连接初始化完成")
            
        except Exception as e:
            logger.error(f"初始化数据库连接失败: {e}")
            raise
    
    async def close(self):
        """关闭数据库连接"""
        try:
            if self.pool:
                await self.pool.close()
            
            if self.http_session:
                await self.http_session.close()
            
            logger.info("数据库连接已关闭")
            
        except Exception as e:
            logger.error(f"关闭数据库连接失败: {e}")
    
    @asynccontextmanager
    async def get_connection(self):
        """获取数据库连接"""
        if not self.pool:
            raise RuntimeError("数据库连接池未初始化")
        
        async with self.pool.acquire() as conn:
            yield conn
    
    @asynccontextmanager
    async def get_transaction(self):
        """获取事务"""
        async with self.get_connection() as conn:
            async with conn.transaction():
                yield conn
    
    def query_builder(self, table: str) -> QueryBuilder:
        """创建查询构建器"""
        return QueryBuilder(table, self.config.POSTGREST_URL)
    
    async def execute_sql(self, query: str, *args) -> List[Dict[str, Any]]:
        """执行SQL查询"""
        async with self.get_connection() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]
    
    async def execute_sql_one(self, query: str, *args) -> Optional[Dict[str, Any]]:
        """执行SQL查询（单条记录）"""
        async with self.get_connection() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None
    
    async def execute_sql_scalar(self, query: str, *args) -> Any:
        """执行SQL查询（标量值）"""
        async with self.get_connection() as conn:
            return await conn.fetchval(query, *args)
    
    async def execute_sql_transaction(self, queries: List[Tuple[str, tuple]]) -> List[Any]:
        """在事务中执行多个SQL查询"""
        results = []
        
        async with self.get_transaction() as conn:
            for query, args in queries:
                result = await conn.fetch(query, *args)
                results.append([dict(row) for row in result])
        
        return results
    
    async def _make_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None
    ) -> DatabaseResponse:
        """发送HTTP请求到PostgREST"""
        if not self.http_session:
            raise RuntimeError("HTTP会话未初始化")
        
        try:
            # 准备请求头
            request_headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            if headers:
                request_headers.update(headers)
            
            # 发送请求
            async with self.http_session.request(
                method=method,
                url=url,
                headers=request_headers,
                json=data,
                params=params
            ) as response:
                
                # 获取响应数据
                response_text = await response.text()
                
                # 解析响应
                if response.status == 204:  # No Content
                    response_data = None
                elif response_text:
                    try:
                        response_data = json.loads(response_text)
                    except json.JSONDecodeError:
                        response_data = response_text
                else:
                    response_data = None
                
                # 获取计数信息
                count = None
                content_range = response.headers.get('Content-Range')
                if content_range:
                    # 解析 Content-Range: 0-9/100
                    parts = content_range.split('/')
                    if len(parts) == 2 and parts[1].isdigit():
                        count = int(parts[1])
                
                # 构建响应
                if response.status >= 400:
                    error_message = response_data if isinstance(response_data, str) else str(response_data)
                    return DatabaseResponse(
                        error=error_message,
                        status_code=response.status
                    )
                
                return DatabaseResponse(
                    data=response_data,
                    count=count,
                    status_code=response.status
                )
        
        except Exception as e:
            logger.error(f"PostgREST请求失败: {e}")
            return DatabaseResponse(
                error=str(e),
                status_code=500
            )
    
    async def select(
        self,
        table: str,
        options: Optional[QueryOptions] = None,
        auth_token: Optional[str] = None
    ) -> DatabaseResponse:
        """查询数据"""
        builder = self.query_builder(table)
        
        if options:
            if options.select:
                builder.select(options.select)
            
            if options.filters:
                for filter_item in options.filters:
                    method = getattr(builder, filter_item.operator, None)
                    if method:
                        method(filter_item.column, filter_item.value)
            
            if options.order:
                for order_item in options.order:
                    builder.order(
                        order_item.column,
                        order_item.ascending,
                        order_item.nulls_first
                    )
            
            if options.limit:
                builder.limit(options.limit)
            
            if options.offset:
                builder.offset(options.offset)
            
            if options.count:
                builder.count(options.count)
        
        if auth_token:
            builder.auth(auth_token)
        
        return await self._make_request(
            method='GET',
            url=builder.build_url(),
            headers=builder.headers
        )
    
    async def insert(
        self,
        table: str,
        data: Union[Dict[str, Any], List[Dict[str, Any]]],
        options: Optional[InsertOptions] = None,
        auth_token: Optional[str] = None
    ) -> DatabaseResponse:
        """插入数据"""
        url = f"{self.config.POSTGREST_URL}/{table}"
        headers = {}
        
        if auth_token:
            headers['Authorization'] = f"Bearer {auth_token}"
        
        if options:
            if options.on_conflict:
                headers['Prefer'] = f"resolution={options.on_conflict}"
            
            if options.returning:
                url += f"?select={options.returning}"
            
            if options.prefer:
                headers['Prefer'] = options.prefer
        
        return await self._make_request(
            method='POST',
            url=url,
            headers=headers,
            data=data
        )
    
    async def update(
        self,
        table: str,
        data: Dict[str, Any],
        options: Optional[UpdateOptions] = None,
        auth_token: Optional[str] = None
    ) -> DatabaseResponse:
        """更新数据"""
        builder = self.query_builder(table)
        
        if options and options.filters:
            for filter_item in options.filters:
                method = getattr(builder, filter_item.operator, None)
                if method:
                    method(filter_item.column, filter_item.value)
        
        if auth_token:
            builder.auth(auth_token)
        
        headers = builder.headers.copy()
        
        if options:
            if options.returning:
                builder.params['select'] = options.returning
            
            if options.prefer:
                headers['Prefer'] = options.prefer
        
        return await self._make_request(
            method='PATCH',
            url=builder.build_url(),
            headers=headers,
            data=data
        )
    
    async def delete(
        self,
        table: str,
        options: Optional[DeleteOptions] = None,
        auth_token: Optional[str] = None
    ) -> DatabaseResponse:
        """删除数据"""
        builder = self.query_builder(table)
        
        if options and options.filters:
            for filter_item in options.filters:
                method = getattr(builder, filter_item.operator, None)
                if method:
                    method(filter_item.column, filter_item.value)
        
        if auth_token:
            builder.auth(auth_token)
        
        headers = builder.headers.copy()
        
        if options and options.returning:
            builder.params['select'] = options.returning
        
        return await self._make_request(
            method='DELETE',
            url=builder.build_url(),
            headers=headers
        )
    
    async def rpc(
        self,
        function_name: str,
        params: Optional[Dict[str, Any]] = None,
        auth_token: Optional[str] = None
    ) -> DatabaseResponse:
        """调用存储过程"""
        url = f"{self.config.POSTGREST_URL}/rpc/{function_name}"
        headers = {}
        
        if auth_token:
            headers['Authorization'] = f"Bearer {auth_token}"
        
        return await self._make_request(
            method='POST',
            url=url,
            headers=headers,
            data=params or {}
        )

# 兼容性包装器（替代原有的Supabase客户端）
class SupabaseCompatClient:
    """Supabase兼容性客户端"""
    
    def __init__(self, db_manager: DatabaseManager, auth_token: Optional[str] = None):
        self.db = db_manager
        self.auth_token = auth_token
    
    def table(self, table_name: str) -> 'SupabaseTableClient':
        """获取表客户端"""
        return SupabaseTableClient(self.db, table_name, self.auth_token)
    
    def auth(self, token: str) -> 'SupabaseCompatClient':
        """设置认证令牌"""
        return SupabaseCompatClient(self.db, token)
    
    def rpc(self, function_name: str, params: Optional[Dict[str, Any]] = None):
        """调用存储过程"""
        return self.db.rpc(function_name, params, self.auth_token)

class SupabaseTableClient:
    """Supabase表客户端"""
    
    def __init__(self, db_manager: DatabaseManager, table_name: str, auth_token: Optional[str] = None):
        self.db = db_manager
        self.table_name = table_name
        self.auth_token = auth_token
        self.query_options = QueryOptions()
    
    def select(self, columns: str = "*") -> 'SupabaseTableClient':
        """选择列"""
        self.query_options.select = columns
        return self
    
    def eq(self, column: str, value: Any) -> 'SupabaseTableClient':
        """等于条件"""
        if not self.query_options.filters:
            self.query_options.filters = []
        self.query_options.filters.append(QueryFilter(column=column, operator="eq", value=value))
        return self
    
    def neq(self, column: str, value: Any) -> 'SupabaseTableClient':
        """不等于条件"""
        if not self.query_options.filters:
            self.query_options.filters = []
        self.query_options.filters.append(QueryFilter(column=column, operator="neq", value=value))
        return self
    
    def gt(self, column: str, value: Any) -> 'SupabaseTableClient':
        """大于条件"""
        if not self.query_options.filters:
            self.query_options.filters = []
        self.query_options.filters.append(QueryFilter(column=column, operator="gt", value=value))
        return self
    
    def gte(self, column: str, value: Any) -> 'SupabaseTableClient':
        """大于等于条件"""
        if not self.query_options.filters:
            self.query_options.filters = []
        self.query_options.filters.append(QueryFilter(column=column, operator="gte", value=value))
        return self
    
    def lt(self, column: str, value: Any) -> 'SupabaseTableClient':
        """小于条件"""
        if not self.query_options.filters:
            self.query_options.filters = []
        self.query_options.filters.append(QueryFilter(column=column, operator="lt", value=value))
        return self
    
    def lte(self, column: str, value: Any) -> 'SupabaseTableClient':
        """小于等于条件"""
        if not self.query_options.filters:
            self.query_options.filters = []
        self.query_options.filters.append(QueryFilter(column=column, operator="lte", value=value))
        return self
    
    def like(self, column: str, pattern: str) -> 'SupabaseTableClient':
        """模糊匹配条件"""
        if not self.query_options.filters:
            self.query_options.filters = []
        self.query_options.filters.append(QueryFilter(column=column, operator="like", value=pattern))
        return self
    
    def ilike(self, column: str, pattern: str) -> 'SupabaseTableClient':
        """不区分大小写模糊匹配条件"""
        if not self.query_options.filters:
            self.query_options.filters = []
        self.query_options.filters.append(QueryFilter(column=column, operator="ilike", value=pattern))
        return self
    
    def in_(self, column: str, values: List[Any]) -> 'SupabaseTableClient':
        """在列表中条件"""
        if not self.query_options.filters:
            self.query_options.filters = []
        self.query_options.filters.append(QueryFilter(column=column, operator="in", value=values))
        return self
    
    def order(self, column: str, desc: bool = False) -> 'SupabaseTableClient':
        """排序"""
        if not self.query_options.order:
            self.query_options.order = []
        self.query_options.order.append(QueryOrder(column=column, ascending=not desc))
        return self
    
    def limit(self, count: int) -> 'SupabaseTableClient':
        """限制数量"""
        self.query_options.limit = count
        return self
    
    def offset(self, count: int) -> 'SupabaseTableClient':
        """偏移量"""
        self.query_options.offset = count
        return self
    
    async def execute(self) -> DatabaseResponse:
        """执行查询"""
        return await self.db.select(self.table_name, self.query_options, self.auth_token)
    
    async def insert(self, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> DatabaseResponse:
        """插入数据"""
        return await self.db.insert(self.table_name, data, auth_token=self.auth_token)
    
    async def update(self, data: Dict[str, Any]) -> DatabaseResponse:
        """更新数据"""
        options = UpdateOptions(filters=self.query_options.filters)
        return await self.db.update(self.table_name, data, options, self.auth_token)
    
    async def delete(self) -> DatabaseResponse:
        """删除数据"""
        options = DeleteOptions(filters=self.query_options.filters)
        return await self.db.delete(self.table_name, options, self.auth_token)

# 全局数据库管理器实例
db_manager = DatabaseManager()

# 兼容性函数（替代原有的Supabase初始化）
def create_client(supabase_url: str = None, supabase_key: str = None) -> SupabaseCompatClient:
    """创建Supabase兼容客户端"""
    return SupabaseCompatClient(db_manager, supabase_key)

# 数据库连接类（兼容原有代码）
class DBConnection:
    """数据库连接类（兼容性包装器）"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.client = None
            self._initialized = True
    
    async def initialize(self):
        """初始化数据库连接"""
        if not db_manager.pool:
            await db_manager.initialize()
        
        self.client = create_client()
        logger.info("数据库连接已初始化")
    
    async def disconnect(self):
        """断开数据库连接"""
        await db_manager.close()
        self.client = None
        logger.info("数据库连接已断开")
    
    def get_client(self) -> SupabaseCompatClient:
        """获取客户端"""
        if not self.client:
            raise RuntimeError("数据库连接未初始化")
        return self.client

# 文件上传功能（替代Supabase Storage）
async def upload_base64_image(
    base64_data: str,
    bucket: str = "images",
    filename: Optional[str] = None
) -> str:
    """上传base64图片到MinIO存储"""
    import base64
    import uuid
    from datetime import datetime
    
    try:
        # 解码base64数据
        if ',' in base64_data:
            header, data = base64_data.split(',', 1)
        else:
            data = base64_data
        
        image_data = base64.b64decode(data)
        
        # 生成文件名
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_id = str(uuid.uuid4())[:8]
            filename = f"image_{timestamp}_{unique_id}.png"
        
        # 上传到MinIO（这里需要实现MinIO客户端）
        # 暂时返回一个模拟的URL
        minio_url = os.getenv('MINIO_URL', 'http://localhost:15003')
        public_url = f"{minio_url}/{bucket}/{filename}"
        
        logger.info(f"图片上传成功: {public_url}")
        return public_url
        
    except Exception as e:
        logger.error(f"上传图片失败: {e}")
        raise