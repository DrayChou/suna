#!/usr/bin/env python3
"""
Suna 实时通信服务
替代 Supabase 的实时功能，提供 WebSocket 连接和实时数据同步

主要功能：
- WebSocket 连接管理
- 实时消息广播
- 房间/频道管理
- 用户认证和授权
- 消息持久化
- 连接状态监控
- 自动重连支持
"""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any, Union

import redis.asyncio as aioredis
import jwt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
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
    HOST = os.getenv('REALTIME_HOST', '0.0.0.0')
    PORT = int(os.getenv('REALTIME_PORT', 8003))
    
    # JWT 配置
    JWT_SECRET = os.getenv('JWT_SECRET', 'your-super-secret-jwt-token')
    JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')
    JWT_EXPIRE_HOURS = int(os.getenv('JWT_EXPIRE_HOURS', 24))
    
    # Redis 配置
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
    REDIS_PREFIX = os.getenv('REDIS_PREFIX', 'suna:realtime')
    
    # WebSocket 配置
    MAX_CONNECTIONS_PER_USER = int(os.getenv('MAX_CONNECTIONS_PER_USER', 10))
    MAX_MESSAGE_SIZE = int(os.getenv('MAX_MESSAGE_SIZE', 64 * 1024))  # 64KB
    HEARTBEAT_INTERVAL = int(os.getenv('HEARTBEAT_INTERVAL', 30))  # 30秒
    CONNECTION_TIMEOUT = int(os.getenv('CONNECTION_TIMEOUT', 300))  # 5分钟
    
    # 安全配置
    ALLOWED_ORIGINS = os.getenv('CORS_ORIGINS', 'http://localhost:3000,http://localhost:8000').split(',')
    
    # 消息持久化配置
    MESSAGE_RETENTION_DAYS = int(os.getenv('MESSAGE_RETENTION_DAYS', 7))
    MAX_MESSAGES_PER_CHANNEL = int(os.getenv('MAX_MESSAGES_PER_CHANNEL', 1000))

# Pydantic 模型
class WebSocketMessage(BaseModel):
    """WebSocket 消息"""
    type: str = Field(..., description="消息类型")
    channel: Optional[str] = Field(default=None, description="频道名称")
    event: Optional[str] = Field(default=None, description="事件名称")
    payload: Optional[Dict[str, Any]] = Field(default=None, description="消息载荷")
    timestamp: Optional[datetime] = Field(default=None, description="时间戳")
    message_id: Optional[str] = Field(default=None, description="消息ID")

class ChannelSubscription(BaseModel):
    """频道订阅"""
    channel: str = Field(..., description="频道名称")
    event: Optional[str] = Field(default="*", description="事件过滤器")
    config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="订阅配置")

class BroadcastMessage(BaseModel):
    """广播消息"""
    channel: str = Field(..., description="频道名称")
    event: str = Field(..., description="事件名称")
    payload: Dict[str, Any] = Field(..., description="消息载荷")
    exclude_user_ids: Optional[List[str]] = Field(default=None, description="排除的用户ID")
    include_user_ids: Optional[List[str]] = Field(default=None, description="包含的用户ID")
    persist: bool = Field(default=True, description="是否持久化")

class ConnectionInfo(BaseModel):
    """连接信息"""
    connection_id: str
    user_id: Optional[str]
    connected_at: datetime
    last_seen: datetime
    channels: List[str]
    user_agent: Optional[str]
    ip_address: Optional[str]

class ChannelStats(BaseModel):
    """频道统计"""
    channel: str
    subscriber_count: int
    message_count: int
    last_activity: Optional[datetime]

# 连接管理器
class ConnectionManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        # 活跃连接: connection_id -> WebSocketConnection
        self.active_connections: Dict[str, 'WebSocketConnection'] = {}
        
        # 用户连接映射: user_id -> Set[connection_id]
        self.user_connections: Dict[str, Set[str]] = {}
        
        # 频道订阅: channel -> Set[connection_id]
        self.channel_subscriptions: Dict[str, Set[str]] = {}
        
        # Redis 连接
        self.redis: Optional[aioredis.Redis] = None
        
        # 心跳任务
        self.heartbeat_task: Optional[asyncio.Task] = None
        
        # 清理任务
        self.cleanup_task: Optional[asyncio.Task] = None
    
    async def initialize(self):
        """初始化连接管理器"""
        try:
            # 连接 Redis
            self.redis = aioredis.from_url(Config.REDIS_URL)
            await self.redis.ping()
            
            # 启动心跳任务
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            # 启动清理任务
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())
            
            logger.info("连接管理器初始化完成")
            
        except Exception as e:
            logger.error(f"初始化连接管理器失败: {e}")
            raise
    
    async def connect(self, websocket: WebSocket, user_id: Optional[str] = None) -> str:
        """建立新连接"""
        connection_id = str(uuid.uuid4())
        
        # 检查用户连接数限制
        if user_id:
            user_connection_count = len(self.user_connections.get(user_id, set()))
            if user_connection_count >= Config.MAX_CONNECTIONS_PER_USER:
                raise HTTPException(
                    status_code=429,
                    detail=f"用户连接数超过限制 ({Config.MAX_CONNECTIONS_PER_USER})"
                )
        
        # 创建连接对象
        connection = WebSocketConnection(
            connection_id=connection_id,
            websocket=websocket,
            user_id=user_id,
            manager=self
        )
        
        # 接受 WebSocket 连接
        await websocket.accept()
        
        # 注册连接
        self.active_connections[connection_id] = connection
        
        if user_id:
            if user_id not in self.user_connections:
                self.user_connections[user_id] = set()
            self.user_connections[user_id].add(connection_id)
        
        # 在 Redis 中记录连接
        await self._store_connection_info(connection)
        
        logger.info(f"新连接建立: {connection_id}, 用户: {user_id}")
        
        # 发送连接确认消息
        await connection.send_message({
            "type": "connection_ack",
            "connection_id": connection_id,
            "timestamp": datetime.now().isoformat()
        })
        
        return connection_id
    
    async def disconnect(self, connection_id: str):
        """断开连接"""
        if connection_id not in self.active_connections:
            return
        
        connection = self.active_connections[connection_id]
        user_id = connection.user_id
        
        # 取消所有频道订阅
        for channel in list(connection.subscribed_channels):
            await self.unsubscribe_channel(connection_id, channel)
        
        # 从用户连接映射中移除
        if user_id and user_id in self.user_connections:
            self.user_connections[user_id].discard(connection_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
        
        # 从活跃连接中移除
        del self.active_connections[connection_id]
        
        # 从 Redis 中移除连接信息
        await self._remove_connection_info(connection_id)
        
        logger.info(f"连接断开: {connection_id}, 用户: {user_id}")
    
    async def subscribe_channel(self, connection_id: str, subscription: ChannelSubscription):
        """订阅频道"""
        if connection_id not in self.active_connections:
            raise ValueError("连接不存在")
        
        connection = self.active_connections[connection_id]
        channel = subscription.channel
        
        # 添加到频道订阅
        if channel not in self.channel_subscriptions:
            self.channel_subscriptions[channel] = set()
        self.channel_subscriptions[channel].add(connection_id)
        
        # 添加到连接的订阅列表
        connection.subscribed_channels.add(channel)
        connection.channel_configs[channel] = subscription.config
        
        # 在 Redis 中记录订阅
        await self.redis.sadd(f"{Config.REDIS_PREFIX}:channel:{channel}:subscribers", connection_id)
        
        logger.info(f"连接 {connection_id} 订阅频道: {channel}")
        
        # 发送订阅确认
        await connection.send_message({
            "type": "subscription_ack",
            "channel": channel,
            "timestamp": datetime.now().isoformat()
        })
        
        # 发送频道历史消息（如果配置了）
        if subscription.config.get("send_history", False):
            await self._send_channel_history(connection, channel)
    
    async def unsubscribe_channel(self, connection_id: str, channel: str):
        """取消订阅频道"""
        if connection_id not in self.active_connections:
            return
        
        connection = self.active_connections[connection_id]
        
        # 从频道订阅中移除
        if channel in self.channel_subscriptions:
            self.channel_subscriptions[channel].discard(connection_id)
            if not self.channel_subscriptions[channel]:
                del self.channel_subscriptions[channel]
        
        # 从连接的订阅列表中移除
        connection.subscribed_channels.discard(channel)
        connection.channel_configs.pop(channel, None)
        
        # 从 Redis 中移除订阅
        await self.redis.srem(f"{Config.REDIS_PREFIX}:channel:{channel}:subscribers", connection_id)
        
        logger.info(f"连接 {connection_id} 取消订阅频道: {channel}")
        
        # 发送取消订阅确认
        await connection.send_message({
            "type": "unsubscription_ack",
            "channel": channel,
            "timestamp": datetime.now().isoformat()
        })
    
    async def broadcast_to_channel(self, message: BroadcastMessage):
        """向频道广播消息"""
        channel = message.channel
        
        # 生成消息ID
        message_id = str(uuid.uuid4())
        
        # 构建消息
        ws_message = {
            "type": "broadcast",
            "channel": channel,
            "event": message.event,
            "payload": message.payload,
            "message_id": message_id,
            "timestamp": datetime.now().isoformat()
        }
        
        # 持久化消息
        if message.persist:
            await self._persist_message(channel, ws_message)
        
        # 获取频道订阅者
        subscribers = self.channel_subscriptions.get(channel, set())
        
        # 过滤订阅者
        if message.include_user_ids:
            # 只发送给指定用户
            filtered_subscribers = set()
            for user_id in message.include_user_ids:
                user_connections = self.user_connections.get(user_id, set())
                filtered_subscribers.update(user_connections & subscribers)
            subscribers = filtered_subscribers
        
        if message.exclude_user_ids:
            # 排除指定用户
            excluded_connections = set()
            for user_id in message.exclude_user_ids:
                user_connections = self.user_connections.get(user_id, set())
                excluded_connections.update(user_connections)
            subscribers = subscribers - excluded_connections
        
        # 发送消息
        sent_count = 0
        failed_count = 0
        
        for connection_id in subscribers:
            if connection_id in self.active_connections:
                try:
                    connection = self.active_connections[connection_id]
                    await connection.send_message(ws_message)
                    sent_count += 1
                except Exception as e:
                    logger.error(f"发送消息到连接 {connection_id} 失败: {e}")
                    failed_count += 1
        
        logger.info(f"频道 {channel} 广播完成: 发送 {sent_count}, 失败 {failed_count}")
        
        return {
            "message_id": message_id,
            "sent_count": sent_count,
            "failed_count": failed_count
        }
    
    async def send_to_user(self, user_id: str, message: Dict[str, Any]):
        """发送消息给特定用户"""
        user_connections = self.user_connections.get(user_id, set())
        
        sent_count = 0
        failed_count = 0
        
        for connection_id in user_connections:
            if connection_id in self.active_connections:
                try:
                    connection = self.active_connections[connection_id]
                    await connection.send_message(message)
                    sent_count += 1
                except Exception as e:
                    logger.error(f"发送消息到用户 {user_id} 连接 {connection_id} 失败: {e}")
                    failed_count += 1
        
        return {
            "sent_count": sent_count,
            "failed_count": failed_count
        }
    
    async def get_connection_info(self, connection_id: str) -> Optional[ConnectionInfo]:
        """获取连接信息"""
        if connection_id not in self.active_connections:
            return None
        
        connection = self.active_connections[connection_id]
        
        return ConnectionInfo(
            connection_id=connection_id,
            user_id=connection.user_id,
            connected_at=connection.connected_at,
            last_seen=connection.last_seen,
            channels=list(connection.subscribed_channels),
            user_agent=connection.user_agent,
            ip_address=connection.ip_address
        )
    
    async def get_channel_stats(self, channel: str) -> ChannelStats:
        """获取频道统计"""
        subscriber_count = len(self.channel_subscriptions.get(channel, set()))
        
        # 从 Redis 获取消息数量
        message_count = await self.redis.llen(f"{Config.REDIS_PREFIX}:channel:{channel}:messages")
        
        # 获取最后活动时间
        last_activity_str = await self.redis.get(f"{Config.REDIS_PREFIX}:channel:{channel}:last_activity")
        last_activity = None
        if last_activity_str:
            last_activity = datetime.fromisoformat(last_activity_str.decode())
        
        return ChannelStats(
            channel=channel,
            subscriber_count=subscriber_count,
            message_count=message_count,
            last_activity=last_activity
        )
    
    async def list_active_connections(self) -> List[ConnectionInfo]:
        """列出所有活跃连接"""
        connections = []
        
        for connection_id in self.active_connections:
            info = await self.get_connection_info(connection_id)
            if info:
                connections.append(info)
        
        return connections
    
    async def _store_connection_info(self, connection: 'WebSocketConnection'):
        """在 Redis 中存储连接信息"""
        connection_data = {
            "connection_id": connection.connection_id,
            "user_id": connection.user_id or "",
            "connected_at": connection.connected_at.isoformat(),
            "last_seen": connection.last_seen.isoformat(),
            "user_agent": connection.user_agent or "",
            "ip_address": connection.ip_address or ""
        }
        
        await self.redis.hset(
            f"{Config.REDIS_PREFIX}:connection:{connection.connection_id}",
            mapping=connection_data
        )
        
        # 设置过期时间
        await self.redis.expire(
            f"{Config.REDIS_PREFIX}:connection:{connection.connection_id}",
            Config.CONNECTION_TIMEOUT
        )
    
    async def _remove_connection_info(self, connection_id: str):
        """从 Redis 中移除连接信息"""
        await self.redis.delete(f"{Config.REDIS_PREFIX}:connection:{connection_id}")
    
    async def _persist_message(self, channel: str, message: Dict[str, Any]):
        """持久化消息"""
        message_key = f"{Config.REDIS_PREFIX}:channel:{channel}:messages"
        
        # 添加消息到列表
        await self.redis.lpush(message_key, json.dumps(message, default=str))
        
        # 限制消息数量
        await self.redis.ltrim(message_key, 0, Config.MAX_MESSAGES_PER_CHANNEL - 1)
        
        # 设置过期时间
        await self.redis.expire(message_key, Config.MESSAGE_RETENTION_DAYS * 24 * 3600)
        
        # 更新频道最后活动时间
        await self.redis.set(
            f"{Config.REDIS_PREFIX}:channel:{channel}:last_activity",
            datetime.now().isoformat(),
            ex=Config.MESSAGE_RETENTION_DAYS * 24 * 3600
        )
    
    async def _send_channel_history(self, connection: 'WebSocketConnection', channel: str):
        """发送频道历史消息"""
        try:
            message_key = f"{Config.REDIS_PREFIX}:channel:{channel}:messages"
            
            # 获取最近的消息（最多50条）
            messages = await self.redis.lrange(message_key, 0, 49)
            
            # 反转消息顺序（最旧的在前）
            messages.reverse()
            
            for message_data in messages:
                try:
                    message = json.loads(message_data)
                    message["type"] = "history"
                    await connection.send_message(message)
                except Exception as e:
                    logger.error(f"发送历史消息失败: {e}")
            
            # 发送历史消息结束标记
            await connection.send_message({
                "type": "history_end",
                "channel": channel,
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"发送频道 {channel} 历史消息失败: {e}")
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        while True:
            try:
                current_time = datetime.now()
                disconnected_connections = []
                
                for connection_id, connection in self.active_connections.items():
                    try:
                        # 发送心跳
                        await connection.send_message({
                            "type": "heartbeat",
                            "timestamp": current_time.isoformat()
                        })
                        
                        # 检查连接超时
                        if (current_time - connection.last_seen).total_seconds() > Config.CONNECTION_TIMEOUT:
                            disconnected_connections.append(connection_id)
                        
                    except Exception as e:
                        logger.warning(f"心跳检查连接 {connection_id} 失败: {e}")
                        disconnected_connections.append(connection_id)
                
                # 清理超时连接
                for connection_id in disconnected_connections:
                    await self.disconnect(connection_id)
                
                await asyncio.sleep(Config.HEARTBEAT_INTERVAL)
                
            except Exception as e:
                logger.error(f"心跳循环异常: {e}")
                await asyncio.sleep(Config.HEARTBEAT_INTERVAL)
    
    async def _cleanup_loop(self):
        """清理循环"""
        while True:
            try:
                # 清理过期的消息和连接信息
                current_time = datetime.now()
                
                # 这里可以添加更多清理逻辑
                
                # 每小时执行一次清理
                await asyncio.sleep(3600)
                
            except Exception as e:
                logger.error(f"清理循环异常: {e}")
                await asyncio.sleep(3600)
    
    async def cleanup(self):
        """清理资源"""
        try:
            # 取消任务
            if self.heartbeat_task:
                self.heartbeat_task.cancel()
            
            if self.cleanup_task:
                self.cleanup_task.cancel()
            
            # 断开所有连接
            for connection_id in list(self.active_connections.keys()):
                await self.disconnect(connection_id)
            
            # 关闭 Redis 连接
            if self.redis:
                await self.redis.close()
            
            logger.info("连接管理器资源清理完成")
            
        except Exception as e:
            logger.error(f"清理连接管理器资源失败: {e}")

# WebSocket 连接类
class WebSocketConnection:
    """WebSocket 连接"""
    
    def __init__(self, connection_id: str, websocket: WebSocket, user_id: Optional[str], manager: ConnectionManager):
        self.connection_id = connection_id
        self.websocket = websocket
        self.user_id = user_id
        self.manager = manager
        
        self.connected_at = datetime.now()
        self.last_seen = datetime.now()
        
        self.subscribed_channels: Set[str] = set()
        self.channel_configs: Dict[str, Dict[str, Any]] = {}
        
        # 从 WebSocket 获取客户端信息
        self.user_agent = None
        self.ip_address = None
        
        if hasattr(websocket, 'headers'):
            self.user_agent = websocket.headers.get('user-agent')
        
        if hasattr(websocket, 'client'):
            self.ip_address = websocket.client.host
    
    async def send_message(self, message: Dict[str, Any]):
        """发送消息"""
        try:
            await self.websocket.send_text(json.dumps(message, default=str))
            self.last_seen = datetime.now()
        except Exception as e:
            logger.error(f"发送消息到连接 {self.connection_id} 失败: {e}")
            raise
    
    async def receive_message(self) -> Optional[Dict[str, Any]]:
        """接收消息"""
        try:
            data = await self.websocket.receive_text()
            
            # 检查消息大小
            if len(data.encode('utf-8')) > Config.MAX_MESSAGE_SIZE:
                raise ValueError("消息过大")
            
            message = json.loads(data)
            self.last_seen = datetime.now()
            
            return message
        except Exception as e:
            logger.error(f"接收连接 {self.connection_id} 消息失败: {e}")
            raise

# 认证
security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[str]:
    """验证JWT令牌"""
    try:
        token = credentials.credentials
        payload = jwt.decode(token, Config.JWT_SECRET, algorithms=[Config.JWT_ALGORITHM])
        user_id = payload.get('sub')
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效令牌")

def optional_verify_token(authorization: Optional[str] = None) -> Optional[str]:
    """可选的令牌验证（用于WebSocket）"""
    if not authorization:
        return None
    
    try:
        # 移除 "Bearer " 前缀
        if authorization.startswith('Bearer '):
            token = authorization[7:]
        else:
            token = authorization
        
        payload = jwt.decode(token, Config.JWT_SECRET, algorithms=[Config.JWT_ALGORITHM])
        return payload.get('sub')
    except Exception:
        return None

# 全局连接管理器实例
connection_manager = ConnectionManager()

# FastAPI 应用
app = FastAPI(
    title="Suna 实时通信服务",
    description="提供 WebSocket 连接和实时数据同步",
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

# WebSocket 路由
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    """WebSocket 连接端点"""
    user_id = optional_verify_token(token)
    
    try:
        # 建立连接
        connection_id = await connection_manager.connect(websocket, user_id)
        connection = connection_manager.active_connections[connection_id]
        
        # 消息处理循环
        while True:
            try:
                # 接收消息
                message = await connection.receive_message()
                
                if not message or 'type' not in message:
                    continue
                
                message_type = message['type']
                
                # 处理不同类型的消息
                if message_type == 'subscribe':
                    # 订阅频道
                    channel = message.get('channel')
                    if channel:
                        subscription = ChannelSubscription(
                            channel=channel,
                            event=message.get('event', '*'),
                            config=message.get('config', {})
                        )
                        await connection_manager.subscribe_channel(connection_id, subscription)
                
                elif message_type == 'unsubscribe':
                    # 取消订阅频道
                    channel = message.get('channel')
                    if channel:
                        await connection_manager.unsubscribe_channel(connection_id, channel)
                
                elif message_type == 'ping':
                    # 响应ping
                    await connection.send_message({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    })
                
                elif message_type == 'broadcast':
                    # 广播消息（需要认证）
                    if user_id:
                        channel = message.get('channel')
                        event = message.get('event')
                        payload = message.get('payload')
                        
                        if channel and event and payload:
                            broadcast_msg = BroadcastMessage(
                                channel=channel,
                                event=event,
                                payload=payload
                            )
                            await connection_manager.broadcast_to_channel(broadcast_msg)
                
                else:
                    logger.warning(f"未知消息类型: {message_type}")
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"处理WebSocket消息失败: {e}")
                await connection.send_message({
                    "type": "error",
                    "message": str(e),
                    "timestamp": datetime.now().isoformat()
                })
    
    except Exception as e:
        logger.error(f"WebSocket连接异常: {e}")
    
    finally:
        # 断开连接
        if 'connection_id' in locals():
            await connection_manager.disconnect(connection_id)

# HTTP API 路由
@app.post("/broadcast")
async def broadcast_message(
    message: BroadcastMessage,
    user_id: str = Depends(verify_token)
):
    """广播消息到频道"""
    result = await connection_manager.broadcast_to_channel(message)
    return result

@app.post("/send/{target_user_id}")
async def send_to_user(
    target_user_id: str,
    message: Dict[str, Any],
    user_id: str = Depends(verify_token)
):
    """发送消息给特定用户"""
    result = await connection_manager.send_to_user(target_user_id, message)
    return result

@app.get("/connections", response_model=List[ConnectionInfo])
async def list_connections(user_id: str = Depends(verify_token)):
    """列出活跃连接"""
    return await connection_manager.list_active_connections()

@app.get("/connections/{connection_id}", response_model=ConnectionInfo)
async def get_connection(connection_id: str, user_id: str = Depends(verify_token)):
    """获取连接信息"""
    info = await connection_manager.get_connection_info(connection_id)
    if not info:
        raise HTTPException(status_code=404, detail="连接不存在")
    return info

@app.get("/channels/{channel}/stats", response_model=ChannelStats)
async def get_channel_stats(channel: str, user_id: str = Depends(verify_token)):
    """获取频道统计"""
    return await connection_manager.get_channel_stats(channel)

@app.delete("/connections/{connection_id}")
async def disconnect_connection(connection_id: str, user_id: str = Depends(verify_token)):
    """断开指定连接"""
    await connection_manager.disconnect(connection_id)
    return {"message": "连接已断开"}

@app.get("/health")
async def health_check():
    """健康检查"""
    try:
        # 检查 Redis 连接
        await connection_manager.redis.ping()
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "active_connections": len(connection_manager.active_connections),
            "active_channels": len(connection_manager.channel_subscriptions)
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"服务不健康: {str(e)}")

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化"""
    logger.info("正在启动实时通信服务...")
    await connection_manager.initialize()
    logger.info("实时通信服务启动完成")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理资源"""
    logger.info("正在关闭实时通信服务...")
    await connection_manager.cleanup()
    logger.info("实时通信服务已关闭")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=Config.HOST,
        port=Config.PORT,
        reload=True,
        log_level="info"
    )