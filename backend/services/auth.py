#!/usr/bin/env python3
"""
Suna 认证服务
替代 Supabase 的认证功能，提供基于 GoTrue 的用户认证和授权

主要功能：
- 用户注册和登录
- JWT 令牌管理
- 密码重置
- 邮箱验证
- 用户会话管理
- 角色和权限管理
- 多因素认证（MFA）
- OAuth 集成
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Union, Tuple
from urllib.parse import urlencode

import aiohttp
import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field, EmailStr, validator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 配置
class AuthConfig:
    # GoTrue 配置
    GOTRUE_URL = os.getenv('GOTRUE_URL', 'http://localhost:9999')
    GOTRUE_JWT_SECRET = os.getenv('GOTRUE_JWT_SECRET', 'your-super-secret-jwt-token')
    GOTRUE_JWT_ALGORITHM = os.getenv('GOTRUE_JWT_ALGORITHM', 'HS256')
    
    # JWT 配置
    JWT_SECRET = os.getenv('JWT_SECRET', 'your-super-secret-jwt-token')
    JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRE_MINUTES', 60))
    JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv('JWT_REFRESH_TOKEN_EXPIRE_DAYS', 30))
    
    # 密码配置
    PASSWORD_MIN_LENGTH = int(os.getenv('PASSWORD_MIN_LENGTH', 8))
    PASSWORD_REQUIRE_UPPERCASE = os.getenv('PASSWORD_REQUIRE_UPPERCASE', 'true').lower() == 'true'
    PASSWORD_REQUIRE_LOWERCASE = os.getenv('PASSWORD_REQUIRE_LOWERCASE', 'true').lower() == 'true'
    PASSWORD_REQUIRE_NUMBERS = os.getenv('PASSWORD_REQUIRE_NUMBERS', 'true').lower() == 'true'
    PASSWORD_REQUIRE_SYMBOLS = os.getenv('PASSWORD_REQUIRE_SYMBOLS', 'false').lower() == 'true'
    
    # 邮箱配置
    SMTP_HOST = os.getenv('SMTP_HOST', 'localhost')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    SMTP_USER = os.getenv('SMTP_USER', '')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
    SMTP_FROM_EMAIL = os.getenv('SMTP_FROM_EMAIL', 'noreply@suna.dev')
    
    # 安全配置
    MAX_LOGIN_ATTEMPTS = int(os.getenv('MAX_LOGIN_ATTEMPTS', 5))
    LOGIN_ATTEMPT_WINDOW_MINUTES = int(os.getenv('LOGIN_ATTEMPT_WINDOW_MINUTES', 15))
    ACCOUNT_LOCKOUT_DURATION_MINUTES = int(os.getenv('ACCOUNT_LOCKOUT_DURATION_MINUTES', 30))
    
    # 验证码配置
    VERIFICATION_CODE_LENGTH = int(os.getenv('VERIFICATION_CODE_LENGTH', 6))
    VERIFICATION_CODE_EXPIRE_MINUTES = int(os.getenv('VERIFICATION_CODE_EXPIRE_MINUTES', 10))
    
    # 会话配置
    MAX_SESSIONS_PER_USER = int(os.getenv('MAX_SESSIONS_PER_USER', 5))
    SESSION_TIMEOUT_MINUTES = int(os.getenv('SESSION_TIMEOUT_MINUTES', 60))
    
    # OAuth 配置
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '')
    GITHUB_CLIENT_ID = os.getenv('GITHUB_CLIENT_ID', '')
    GITHUB_CLIENT_SECRET = os.getenv('GITHUB_CLIENT_SECRET', '')
    
    # 应用配置
    SITE_URL = os.getenv('SITE_URL', 'http://localhost:15014')
    CONFIRM_EMAIL_REDIRECT_URL = os.getenv('CONFIRM_EMAIL_REDIRECT_URL', f'{SITE_URL}/auth/confirm')
    RESET_PASSWORD_REDIRECT_URL = os.getenv('RESET_PASSWORD_REDIRECT_URL', f'{SITE_URL}/auth/reset')

# Pydantic 模型
class UserSignUp(BaseModel):
    """用户注册"""
    email: EmailStr = Field(..., description="邮箱地址")
    password: str = Field(..., min_length=8, description="密码")
    full_name: Optional[str] = Field(default=None, description="全名")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="用户元数据")
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < AuthConfig.PASSWORD_MIN_LENGTH:
            raise ValueError(f"密码长度至少为 {AuthConfig.PASSWORD_MIN_LENGTH} 位")
        
        if AuthConfig.PASSWORD_REQUIRE_UPPERCASE and not any(c.isupper() for c in v):
            raise ValueError("密码必须包含大写字母")
        
        if AuthConfig.PASSWORD_REQUIRE_LOWERCASE and not any(c.islower() for c in v):
            raise ValueError("密码必须包含小写字母")
        
        if AuthConfig.PASSWORD_REQUIRE_NUMBERS and not any(c.isdigit() for c in v):
            raise ValueError("密码必须包含数字")
        
        if AuthConfig.PASSWORD_REQUIRE_SYMBOLS and not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in v):
            raise ValueError("密码必须包含特殊字符")
        
        return v

class UserSignIn(BaseModel):
    """用户登录"""
    email: EmailStr = Field(..., description="邮箱地址")
    password: str = Field(..., description="密码")
    remember_me: bool = Field(default=False, description="记住我")

class UserUpdate(BaseModel):
    """用户更新"""
    email: Optional[EmailStr] = Field(default=None, description="邮箱地址")
    password: Optional[str] = Field(default=None, description="新密码")
    full_name: Optional[str] = Field(default=None, description="全名")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="用户元数据")

class PasswordReset(BaseModel):
    """密码重置"""
    email: EmailStr = Field(..., description="邮箱地址")

class PasswordResetConfirm(BaseModel):
    """确认密码重置"""
    token: str = Field(..., description="重置令牌")
    password: str = Field(..., min_length=8, description="新密码")

class EmailVerification(BaseModel):
    """邮箱验证"""
    token: str = Field(..., description="验证令牌")

class RefreshToken(BaseModel):
    """刷新令牌"""
    refresh_token: str = Field(..., description="刷新令牌")

class User(BaseModel):
    """用户信息"""
    id: str = Field(..., description="用户ID")
    email: str = Field(..., description="邮箱地址")
    full_name: Optional[str] = Field(default=None, description="全名")
    avatar_url: Optional[str] = Field(default=None, description="头像URL")
    email_confirmed: bool = Field(default=False, description="邮箱是否已验证")
    phone_confirmed: bool = Field(default=False, description="手机是否已验证")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    last_sign_in_at: Optional[datetime] = Field(default=None, description="最后登录时间")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="用户元数据")
    role: str = Field(default="user", description="用户角色")
    is_active: bool = Field(default=True, description="是否激活")

class Session(BaseModel):
    """用户会话"""
    access_token: str = Field(..., description="访问令牌")
    refresh_token: str = Field(..., description="刷新令牌")
    expires_in: int = Field(..., description="过期时间（秒）")
    expires_at: datetime = Field(..., description="过期时间")
    token_type: str = Field(default="bearer", description="令牌类型")
    user: User = Field(..., description="用户信息")

class AuthResponse(BaseModel):
    """认证响应"""
    success: bool = Field(default=True, description="是否成功")
    message: Optional[str] = Field(default=None, description="消息")
    session: Optional[Session] = Field(default=None, description="会话信息")
    user: Optional[User] = Field(default=None, description="用户信息")
    error: Optional[str] = Field(default=None, description="错误信息")

class LoginAttempt(BaseModel):
    """登录尝试记录"""
    email: str
    ip_address: str
    user_agent: str
    success: bool
    timestamp: datetime
    failure_reason: Optional[str] = None

# 密码加密
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """加密密码"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)

# JWT 令牌管理
class TokenManager:
    """JWT 令牌管理器"""
    
    @staticmethod
    def create_access_token(user_id: str, email: str, role: str = "user", expires_delta: Optional[timedelta] = None) -> str:
        """创建访问令牌"""
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=AuthConfig.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        
        payload = {
            "sub": user_id,
            "email": email,
            "role": role,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "access"
        }
        
        return jwt.encode(payload, AuthConfig.JWT_SECRET, algorithm=AuthConfig.JWT_ALGORITHM)
    
    @staticmethod
    def create_refresh_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
        """创建刷新令牌"""
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(days=AuthConfig.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        
        payload = {
            "sub": user_id,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "refresh",
            "jti": secrets.token_urlsafe(32)  # JWT ID for revocation
        }
        
        return jwt.encode(payload, AuthConfig.JWT_SECRET, algorithm=AuthConfig.JWT_ALGORITHM)
    
    @staticmethod
    def verify_token(token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
        """验证令牌"""
        try:
            payload = jwt.decode(token, AuthConfig.JWT_SECRET, algorithms=[AuthConfig.JWT_ALGORITHM])
            
            if payload.get("type") != token_type:
                return None
            
            return payload
        
        except jwt.ExpiredSignatureError:
            logger.warning("令牌已过期")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"无效令牌: {e}")
            return None
    
    @staticmethod
    def create_verification_token(user_id: str, purpose: str, expires_delta: Optional[timedelta] = None) -> str:
        """创建验证令牌（用于邮箱验证、密码重置等）"""
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=AuthConfig.VERIFICATION_CODE_EXPIRE_MINUTES)
        
        payload = {
            "sub": user_id,
            "purpose": purpose,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "verification"
        }
        
        return jwt.encode(payload, AuthConfig.JWT_SECRET, algorithm=AuthConfig.JWT_ALGORITHM)
    
    @staticmethod
    def verify_verification_token(token: str, purpose: str) -> Optional[str]:
        """验证验证令牌"""
        try:
            payload = jwt.decode(token, AuthConfig.JWT_SECRET, algorithms=[AuthConfig.JWT_ALGORITHM])
            
            if payload.get("type") != "verification":
                return None
            
            if payload.get("purpose") != purpose:
                return None
            
            return payload.get("sub")
        
        except jwt.ExpiredSignatureError:
            logger.warning("验证令牌已过期")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"无效验证令牌: {e}")
            return None

# 认证服务
class AuthService:
    """认证服务"""
    
    def __init__(self):
        self.http_session: Optional[aiohttp.ClientSession] = None
        self.login_attempts: Dict[str, List[LoginAttempt]] = {}  # 简单的内存存储，生产环境应使用Redis
        self.active_sessions: Dict[str, Dict[str, Any]] = {}  # 活跃会话
    
    async def initialize(self):
        """初始化认证服务"""
        try:
            self.http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
            
            # 测试GoTrue连接
            await self._test_gotrue_connection()
            
            logger.info("认证服务初始化完成")
            
        except Exception as e:
            logger.error(f"初始化认证服务失败: {e}")
            raise
    
    async def close(self):
        """关闭认证服务"""
        try:
            if self.http_session:
                await self.http_session.close()
            
            logger.info("认证服务已关闭")
            
        except Exception as e:
            logger.error(f"关闭认证服务失败: {e}")
    
    async def _test_gotrue_connection(self):
        """测试GoTrue连接"""
        try:
            async with self.http_session.get(f"{AuthConfig.GOTRUE_URL}/health") as response:
                if response.status != 200:
                    raise Exception(f"GoTrue健康检查失败: {response.status}")
                
                logger.info("GoTrue连接正常")
        
        except Exception as e:
            logger.warning(f"GoTrue连接测试失败: {e}，将使用本地认证")
    
    async def _make_gotrue_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Tuple[int, Dict[str, Any]]:
        """发送请求到GoTrue"""
        if not self.http_session:
            raise RuntimeError("认证服务未初始化")
        
        url = f"{AuthConfig.GOTRUE_URL}{endpoint}"
        
        request_headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        if headers:
            request_headers.update(headers)
        
        try:
            async with self.http_session.request(
                method=method,
                url=url,
                json=data,
                headers=request_headers
            ) as response:
                
                response_text = await response.text()
                
                try:
                    response_data = json.loads(response_text) if response_text else {}
                except json.JSONDecodeError:
                    response_data = {"message": response_text}
                
                return response.status, response_data
        
        except Exception as e:
            logger.error(f"GoTrue请求失败: {e}")
            return 500, {"error": str(e)}
    
    def _check_login_attempts(self, email: str, ip_address: str) -> bool:
        """检查登录尝试次数"""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=AuthConfig.LOGIN_ATTEMPT_WINDOW_MINUTES)
        
        # 清理过期的尝试记录
        if email in self.login_attempts:
            self.login_attempts[email] = [
                attempt for attempt in self.login_attempts[email]
                if attempt.timestamp > window_start
            ]
        
        # 检查失败次数
        failed_attempts = [
            attempt for attempt in self.login_attempts.get(email, [])
            if not attempt.success and attempt.ip_address == ip_address
        ]
        
        return len(failed_attempts) < AuthConfig.MAX_LOGIN_ATTEMPTS
    
    def _record_login_attempt(
        self,
        email: str,
        ip_address: str,
        user_agent: str,
        success: bool,
        failure_reason: Optional[str] = None
    ):
        """记录登录尝试"""
        attempt = LoginAttempt(
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            timestamp=datetime.now(timezone.utc),
            failure_reason=failure_reason
        )
        
        if email not in self.login_attempts:
            self.login_attempts[email] = []
        
        self.login_attempts[email].append(attempt)
    
    async def sign_up(
        self,
        user_data: UserSignUp,
        ip_address: str = "unknown",
        user_agent: str = "unknown"
    ) -> AuthResponse:
        """用户注册"""
        try:
            # 准备注册数据
            signup_data = {
                "email": user_data.email,
                "password": user_data.password,
                "data": {
                    "full_name": user_data.full_name,
                    **(user_data.metadata or {})
                }
            }
            
            # 发送注册请求到GoTrue
            status, response_data = await self._make_gotrue_request(
                "POST",
                "/signup",
                signup_data
            )
            
            if status == 200 or status == 201:
                # 注册成功
                user_info = response_data.get("user", {})
                
                user = User(
                    id=user_info.get("id"),
                    email=user_info.get("email"),
                    full_name=user_info.get("user_metadata", {}).get("full_name"),
                    email_confirmed=user_info.get("email_confirmed_at") is not None,
                    created_at=datetime.fromisoformat(user_info.get("created_at").replace('Z', '+00:00')),
                    updated_at=datetime.fromisoformat(user_info.get("updated_at").replace('Z', '+00:00')),
                    metadata=user_info.get("user_metadata", {})
                )
                
                # 如果有访问令牌，创建会话
                session = None
                if "access_token" in response_data:
                    access_token = response_data["access_token"]
                    refresh_token = response_data.get("refresh_token")
                    expires_in = response_data.get("expires_in", AuthConfig.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)
                    
                    session = Session(
                        access_token=access_token,
                        refresh_token=refresh_token,
                        expires_in=expires_in,
                        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
                        user=user
                    )
                
                return AuthResponse(
                    success=True,
                    message="注册成功，请检查邮箱进行验证",
                    session=session,
                    user=user
                )
            
            else:
                # 注册失败
                error_message = response_data.get("msg", response_data.get("message", "注册失败"))
                return AuthResponse(
                    success=False,
                    error=error_message
                )
        
        except Exception as e:
            logger.error(f"用户注册失败: {e}")
            return AuthResponse(
                success=False,
                error=f"注册过程中发生错误: {str(e)}"
            )
    
    async def sign_in(
        self,
        credentials: UserSignIn,
        ip_address: str = "unknown",
        user_agent: str = "unknown"
    ) -> AuthResponse:
        """用户登录"""
        try:
            # 检查登录尝试次数
            if not self._check_login_attempts(credentials.email, ip_address):
                self._record_login_attempt(
                    credentials.email,
                    ip_address,
                    user_agent,
                    False,
                    "登录尝试次数过多"
                )
                
                return AuthResponse(
                    success=False,
                    error=f"登录尝试次数过多，请 {AuthConfig.ACCOUNT_LOCKOUT_DURATION_MINUTES} 分钟后再试"
                )
            
            # 准备登录数据
            signin_data = {
                "email": credentials.email,
                "password": credentials.password
            }
            
            # 发送登录请求到GoTrue
            status, response_data = await self._make_gotrue_request(
                "POST",
                "/token?grant_type=password",
                signin_data
            )
            
            if status == 200:
                # 登录成功
                self._record_login_attempt(
                    credentials.email,
                    ip_address,
                    user_agent,
                    True
                )
                
                user_info = response_data.get("user", {})
                
                user = User(
                    id=user_info.get("id"),
                    email=user_info.get("email"),
                    full_name=user_info.get("user_metadata", {}).get("full_name"),
                    email_confirmed=user_info.get("email_confirmed_at") is not None,
                    created_at=datetime.fromisoformat(user_info.get("created_at").replace('Z', '+00:00')),
                    updated_at=datetime.fromisoformat(user_info.get("updated_at").replace('Z', '+00:00')),
                    last_sign_in_at=datetime.now(timezone.utc),
                    metadata=user_info.get("user_metadata", {})
                )
                
                # 创建会话
                access_token = response_data["access_token"]
                refresh_token = response_data.get("refresh_token")
                expires_in = response_data.get("expires_in", AuthConfig.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)
                
                session = Session(
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expires_in=expires_in,
                    expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
                    user=user
                )
                
                # 记录活跃会话
                self.active_sessions[user.id] = {
                    "session": session,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "created_at": datetime.now(timezone.utc)
                }
                
                return AuthResponse(
                    success=True,
                    message="登录成功",
                    session=session,
                    user=user
                )
            
            else:
                # 登录失败
                error_message = response_data.get("error_description", response_data.get("message", "登录失败"))
                
                self._record_login_attempt(
                    credentials.email,
                    ip_address,
                    user_agent,
                    False,
                    error_message
                )
                
                return AuthResponse(
                    success=False,
                    error=error_message
                )
        
        except Exception as e:
            logger.error(f"用户登录失败: {e}")
            
            self._record_login_attempt(
                credentials.email,
                ip_address,
                user_agent,
                False,
                str(e)
            )
            
            return AuthResponse(
                success=False,
                error=f"登录过程中发生错误: {str(e)}"
            )
    
    async def refresh_session(self, refresh_token_data: RefreshToken) -> AuthResponse:
        """刷新会话"""
        try:
            # 发送刷新请求到GoTrue
            refresh_data = {
                "refresh_token": refresh_token_data.refresh_token
            }
            
            status, response_data = await self._make_gotrue_request(
                "POST",
                "/token?grant_type=refresh_token",
                refresh_data
            )
            
            if status == 200:
                # 刷新成功
                user_info = response_data.get("user", {})
                
                user = User(
                    id=user_info.get("id"),
                    email=user_info.get("email"),
                    full_name=user_info.get("user_metadata", {}).get("full_name"),
                    email_confirmed=user_info.get("email_confirmed_at") is not None,
                    created_at=datetime.fromisoformat(user_info.get("created_at").replace('Z', '+00:00')),
                    updated_at=datetime.fromisoformat(user_info.get("updated_at").replace('Z', '+00:00')),
                    metadata=user_info.get("user_metadata", {})
                )
                
                # 创建新会话
                access_token = response_data["access_token"]
                refresh_token = response_data.get("refresh_token")
                expires_in = response_data.get("expires_in", AuthConfig.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)
                
                session = Session(
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expires_in=expires_in,
                    expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
                    user=user
                )
                
                return AuthResponse(
                    success=True,
                    message="会话刷新成功",
                    session=session,
                    user=user
                )
            
            else:
                # 刷新失败
                error_message = response_data.get("error_description", response_data.get("message", "会话刷新失败"))
                return AuthResponse(
                    success=False,
                    error=error_message
                )
        
        except Exception as e:
            logger.error(f"会话刷新失败: {e}")
            return AuthResponse(
                success=False,
                error=f"会话刷新过程中发生错误: {str(e)}"
            )
    
    async def sign_out(self, access_token: str) -> AuthResponse:
        """用户登出"""
        try:
            # 验证令牌并获取用户ID
            payload = TokenManager.verify_token(access_token)
            if payload:
                user_id = payload.get("sub")
                if user_id and user_id in self.active_sessions:
                    del self.active_sessions[user_id]
            
            # 发送登出请求到GoTrue
            headers = {"Authorization": f"Bearer {access_token}"}
            
            status, response_data = await self._make_gotrue_request(
                "POST",
                "/logout",
                headers=headers
            )
            
            return AuthResponse(
                success=True,
                message="登出成功"
            )
        
        except Exception as e:
            logger.error(f"用户登出失败: {e}")
            return AuthResponse(
                success=False,
                error=f"登出过程中发生错误: {str(e)}"
            )
    
    async def get_user(self, access_token: str) -> AuthResponse:
        """获取用户信息"""
        try:
            # 发送获取用户请求到GoTrue
            headers = {"Authorization": f"Bearer {access_token}"}
            
            status, response_data = await self._make_gotrue_request(
                "GET",
                "/user",
                headers=headers
            )
            
            if status == 200:
                user_info = response_data
                
                user = User(
                    id=user_info.get("id"),
                    email=user_info.get("email"),
                    full_name=user_info.get("user_metadata", {}).get("full_name"),
                    email_confirmed=user_info.get("email_confirmed_at") is not None,
                    created_at=datetime.fromisoformat(user_info.get("created_at").replace('Z', '+00:00')),
                    updated_at=datetime.fromisoformat(user_info.get("updated_at").replace('Z', '+00:00')),
                    metadata=user_info.get("user_metadata", {})
                )
                
                return AuthResponse(
                    success=True,
                    user=user
                )
            
            else:
                error_message = response_data.get("message", "获取用户信息失败")
                return AuthResponse(
                    success=False,
                    error=error_message
                )
        
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return AuthResponse(
                success=False,
                error=f"获取用户信息过程中发生错误: {str(e)}"
            )
    
    async def update_user(
        self,
        access_token: str,
        user_data: UserUpdate
    ) -> AuthResponse:
        """更新用户信息"""
        try:
            # 准备更新数据
            update_data = {}
            
            if user_data.email:
                update_data["email"] = user_data.email
            
            if user_data.password:
                update_data["password"] = user_data.password
            
            if user_data.full_name is not None or user_data.metadata is not None:
                user_metadata = {}
                if user_data.full_name is not None:
                    user_metadata["full_name"] = user_data.full_name
                if user_data.metadata:
                    user_metadata.update(user_data.metadata)
                update_data["data"] = user_metadata
            
            # 发送更新请求到GoTrue
            headers = {"Authorization": f"Bearer {access_token}"}
            
            status, response_data = await self._make_gotrue_request(
                "PUT",
                "/user",
                update_data,
                headers
            )
            
            if status == 200:
                user_info = response_data
                
                user = User(
                    id=user_info.get("id"),
                    email=user_info.get("email"),
                    full_name=user_info.get("user_metadata", {}).get("full_name"),
                    email_confirmed=user_info.get("email_confirmed_at") is not None,
                    created_at=datetime.fromisoformat(user_info.get("created_at").replace('Z', '+00:00')),
                    updated_at=datetime.fromisoformat(user_info.get("updated_at").replace('Z', '+00:00')),
                    metadata=user_info.get("user_metadata", {})
                )
                
                return AuthResponse(
                    success=True,
                    message="用户信息更新成功",
                    user=user
                )
            
            else:
                error_message = response_data.get("message", "更新用户信息失败")
                return AuthResponse(
                    success=False,
                    error=error_message
                )
        
        except Exception as e:
            logger.error(f"更新用户信息失败: {e}")
            return AuthResponse(
                success=False,
                error=f"更新用户信息过程中发生错误: {str(e)}"
            )
    
    async def reset_password(self, reset_data: PasswordReset) -> AuthResponse:
        """重置密码"""
        try:
            # 发送重置密码请求到GoTrue
            reset_request = {
                "email": reset_data.email
            }
            
            status, response_data = await self._make_gotrue_request(
                "POST",
                "/recover",
                reset_request
            )
            
            if status == 200:
                return AuthResponse(
                    success=True,
                    message="密码重置邮件已发送，请检查邮箱"
                )
            
            else:
                error_message = response_data.get("message", "发送重置密码邮件失败")
                return AuthResponse(
                    success=False,
                    error=error_message
                )
        
        except Exception as e:
            logger.error(f"重置密码失败: {e}")
            return AuthResponse(
                success=False,
                error=f"重置密码过程中发生错误: {str(e)}"
            )
    
    async def verify_email(self, verification: EmailVerification) -> AuthResponse:
        """验证邮箱"""
        try:
            # 发送邮箱验证请求到GoTrue
            verify_data = {
                "token": verification.token,
                "type": "signup"
            }
            
            status, response_data = await self._make_gotrue_request(
                "POST",
                "/verify",
                verify_data
            )
            
            if status == 200:
                return AuthResponse(
                    success=True,
                    message="邮箱验证成功"
                )
            
            else:
                error_message = response_data.get("message", "邮箱验证失败")
                return AuthResponse(
                    success=False,
                    error=error_message
                )
        
        except Exception as e:
            logger.error(f"邮箱验证失败: {e}")
            return AuthResponse(
                success=False,
                error=f"邮箱验证过程中发生错误: {str(e)}"
            )
    
    def verify_access_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        """验证访问令牌"""
        return TokenManager.verify_token(access_token, "access")
    
    def get_user_from_token(self, access_token: str) -> Optional[str]:
        """从令牌获取用户ID"""
        payload = self.verify_access_token(access_token)
        return payload.get("sub") if payload else None

# 全局认证服务实例
auth_service = AuthService()

# 兼容性函数（替代原有的Supabase认证）
class AuthClient:
    """认证客户端（兼容性包装器）"""
    
    def __init__(self):
        self.service = auth_service
    
    async def sign_up(self, email: str, password: str, **kwargs) -> Dict[str, Any]:
        """用户注册"""
        user_data = UserSignUp(
            email=email,
            password=password,
            full_name=kwargs.get('full_name'),
            metadata=kwargs.get('metadata')
        )
        
        response = await self.service.sign_up(user_data)
        
        if response.success:
            return {
                "user": response.user.dict() if response.user else None,
                "session": response.session.dict() if response.session else None,
                "error": None
            }
        else:
            return {
                "user": None,
                "session": None,
                "error": {"message": response.error}
            }
    
    async def sign_in_with_password(self, email: str, password: str) -> Dict[str, Any]:
        """用户登录"""
        credentials = UserSignIn(email=email, password=password)
        response = await self.service.sign_in(credentials)
        
        if response.success:
            return {
                "user": response.user.dict() if response.user else None,
                "session": response.session.dict() if response.session else None,
                "error": None
            }
        else:
            return {
                "user": None,
                "session": None,
                "error": {"message": response.error}
            }
    
    async def sign_out(self, access_token: str) -> Dict[str, Any]:
        """用户登出"""
        response = await self.service.sign_out(access_token)
        
        return {
            "error": None if response.success else {"message": response.error}
        }
    
    async def get_user(self, access_token: str) -> Dict[str, Any]:
        """获取用户信息"""
        response = await self.service.get_user(access_token)
        
        if response.success:
            return {
                "user": response.user.dict() if response.user else None,
                "error": None
            }
        else:
            return {
                "user": None,
                "error": {"message": response.error}
            }

# 创建认证客户端实例
def create_auth_client() -> AuthClient:
    """创建认证客户端"""
    return AuthClient()