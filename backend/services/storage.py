#!/usr/bin/env python3
"""
Suna 存储服务
替代 Supabase 的存储功能，提供基于 MinIO 的对象存储

主要功能：
- 文件上传和下载
- 图片处理和优化
- 文件元数据管理
- 访问权限控制
- 文件版本管理
- 批量操作
- 文件预览和缩略图
- 存储桶管理
"""

import asyncio
import hashlib
import io
import logging
import mimetypes
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple, BinaryIO
from urllib.parse import quote, unquote

import aiofiles
import aiohttp
from minio import Minio
from minio.error import S3Error
from PIL import Image, ImageOps
from pydantic import BaseModel, Field, validator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 配置
class StorageConfig:
    # MinIO 配置
    MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'localhost:15003')
    MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
    MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'minioadmin')
    MINIO_SECURE = os.getenv('MINIO_SECURE', 'false').lower() == 'true'
    MINIO_REGION = os.getenv('MINIO_REGION', 'us-east-1')
    
    # 存储桶配置
    DEFAULT_BUCKET = os.getenv('STORAGE_DEFAULT_BUCKET', 'suna-storage')
    PUBLIC_BUCKET = os.getenv('STORAGE_PUBLIC_BUCKET', 'suna-public')
    PRIVATE_BUCKET = os.getenv('STORAGE_PRIVATE_BUCKET', 'suna-private')
    TEMP_BUCKET = os.getenv('STORAGE_TEMP_BUCKET', 'suna-temp')
    
    # 文件配置
    MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 100 * 1024 * 1024))  # 100MB
    MAX_IMAGE_SIZE = int(os.getenv('MAX_IMAGE_SIZE', 10 * 1024 * 1024))  # 10MB
    ALLOWED_IMAGE_TYPES = os.getenv('ALLOWED_IMAGE_TYPES', 'jpg,jpeg,png,gif,webp,svg').split(',')
    ALLOWED_FILE_TYPES = os.getenv('ALLOWED_FILE_TYPES', 'pdf,doc,docx,txt,md,json,csv,xlsx').split(',')
    
    # 图片处理配置
    IMAGE_QUALITY = int(os.getenv('IMAGE_QUALITY', 85))
    THUMBNAIL_SIZES = [(150, 150), (300, 300), (600, 600)]
    MAX_IMAGE_DIMENSION = int(os.getenv('MAX_IMAGE_DIMENSION', 2048))
    
    # 缓存配置
    CACHE_CONTROL_PUBLIC = os.getenv('CACHE_CONTROL_PUBLIC', 'public, max-age=31536000')  # 1年
    CACHE_CONTROL_PRIVATE = os.getenv('CACHE_CONTROL_PRIVATE', 'private, max-age=3600')  # 1小时
    
    # URL配置
    PUBLIC_URL_BASE = os.getenv('STORAGE_PUBLIC_URL_BASE', f'http://{MINIO_ENDPOINT}')
    SIGNED_URL_EXPIRE_SECONDS = int(os.getenv('SIGNED_URL_EXPIRE_SECONDS', 3600))  # 1小时
    
    # 临时文件配置
    TEMP_FILE_EXPIRE_HOURS = int(os.getenv('TEMP_FILE_EXPIRE_HOURS', 24))
    CLEANUP_INTERVAL_HOURS = int(os.getenv('CLEANUP_INTERVAL_HOURS', 6))

# Pydantic 模型
class FileUpload(BaseModel):
    """文件上传"""
    filename: str = Field(..., description="文件名")
    content_type: Optional[str] = Field(default=None, description="内容类型")
    bucket: Optional[str] = Field(default=None, description="存储桶")
    path: Optional[str] = Field(default=None, description="存储路径")
    is_public: bool = Field(default=False, description="是否公开")
    metadata: Optional[Dict[str, str]] = Field(default=None, description="文件元数据")
    
    @validator('filename')
    def validate_filename(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("文件名不能为空")
        
        # 检查文件名长度
        if len(v) > 255:
            raise ValueError("文件名过长")
        
        # 检查非法字符
        illegal_chars = ['<', '>', ':', '"', '|', '?', '*', '\\', '/']
        for char in illegal_chars:
            if char in v:
                raise ValueError(f"文件名包含非法字符: {char}")
        
        return v.strip()

class ImageUpload(FileUpload):
    """图片上传"""
    resize: Optional[Tuple[int, int]] = Field(default=None, description="调整大小")
    quality: Optional[int] = Field(default=None, ge=1, le=100, description="图片质量")
    format: Optional[str] = Field(default=None, description="输出格式")
    create_thumbnails: bool = Field(default=True, description="创建缩略图")
    optimize: bool = Field(default=True, description="优化图片")

class FileInfo(BaseModel):
    """文件信息"""
    id: str = Field(..., description="文件ID")
    filename: str = Field(..., description="文件名")
    original_filename: str = Field(..., description="原始文件名")
    content_type: str = Field(..., description="内容类型")
    size: int = Field(..., description="文件大小（字节）")
    bucket: str = Field(..., description="存储桶")
    path: str = Field(..., description="存储路径")
    url: Optional[str] = Field(default=None, description="访问URL")
    public_url: Optional[str] = Field(default=None, description="公开URL")
    is_public: bool = Field(default=False, description="是否公开")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="文件元数据")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    expires_at: Optional[datetime] = Field(default=None, description="过期时间")
    checksum: Optional[str] = Field(default=None, description="文件校验和")
    thumbnails: Optional[List[str]] = Field(default=None, description="缩略图URL列表")

class StorageResponse(BaseModel):
    """存储响应"""
    success: bool = Field(default=True, description="是否成功")
    message: Optional[str] = Field(default=None, description="消息")
    file_info: Optional[FileInfo] = Field(default=None, description="文件信息")
    files: Optional[List[FileInfo]] = Field(default=None, description="文件列表")
    url: Optional[str] = Field(default=None, description="URL")
    urls: Optional[List[str]] = Field(default=None, description="URL列表")
    error: Optional[str] = Field(default=None, description="错误信息")

class BucketInfo(BaseModel):
    """存储桶信息"""
    name: str = Field(..., description="存储桶名称")
    creation_date: datetime = Field(..., description="创建时间")
    is_public: bool = Field(default=False, description="是否公开")
    policy: Optional[str] = Field(default=None, description="访问策略")
    size: Optional[int] = Field(default=None, description="总大小")
    object_count: Optional[int] = Field(default=None, description="对象数量")

# 工具函数
def generate_file_id() -> str:
    """生成文件ID"""
    return str(uuid.uuid4())

def get_file_extension(filename: str) -> str:
    """获取文件扩展名"""
    return Path(filename).suffix.lower().lstrip('.')

def get_content_type(filename: str) -> str:
    """获取内容类型"""
    content_type, _ = mimetypes.guess_type(filename)
    return content_type or 'application/octet-stream'

def is_image(filename: str) -> bool:
    """检查是否为图片文件"""
    ext = get_file_extension(filename)
    return ext in StorageConfig.ALLOWED_IMAGE_TYPES

def is_allowed_file_type(filename: str) -> bool:
    """检查是否为允许的文件类型"""
    ext = get_file_extension(filename)
    return ext in StorageConfig.ALLOWED_FILE_TYPES or ext in StorageConfig.ALLOWED_IMAGE_TYPES

def calculate_checksum(data: bytes) -> str:
    """计算文件校验和"""
    return hashlib.sha256(data).hexdigest()

def sanitize_filename(filename: str) -> str:
    """清理文件名"""
    # 移除路径分隔符
    filename = filename.replace('/', '_').replace('\\', '_')
    
    # 移除特殊字符
    illegal_chars = ['<', '>', ':', '"', '|', '?', '*']
    for char in illegal_chars:
        filename = filename.replace(char, '_')
    
    # 限制长度
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        max_name_length = 255 - len(ext)
        filename = name[:max_name_length] + ext
    
    return filename

def generate_storage_path(user_id: str, filename: str, is_public: bool = False) -> str:
    """生成存储路径"""
    file_id = generate_file_id()
    ext = get_file_extension(filename)
    
    # 按日期分组
    date_path = datetime.now().strftime('%Y/%m/%d')
    
    if is_public:
        return f"public/{date_path}/{file_id}.{ext}"
    else:
        return f"users/{user_id}/{date_path}/{file_id}.{ext}"

# 图片处理
class ImageProcessor:
    """图片处理器"""
    
    @staticmethod
    def optimize_image(
        image_data: bytes,
        max_size: Optional[Tuple[int, int]] = None,
        quality: int = StorageConfig.IMAGE_QUALITY,
        format: Optional[str] = None
    ) -> Tuple[bytes, str]:
        """优化图片"""
        try:
            # 打开图片
            image = Image.open(io.BytesIO(image_data))
            
            # 转换RGBA到RGB（如果需要）
            if image.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            
            # 自动旋转（基于EXIF）
            image = ImageOps.exif_transpose(image)
            
            # 调整大小
            if max_size:
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
            elif max(image.size) > StorageConfig.MAX_IMAGE_DIMENSION:
                # 限制最大尺寸
                ratio = StorageConfig.MAX_IMAGE_DIMENSION / max(image.size)
                new_size = tuple(int(dim * ratio) for dim in image.size)
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            
            # 确定输出格式
            if not format:
                format = 'JPEG' if image.mode == 'RGB' else 'PNG'
            
            # 保存优化后的图片
            output = io.BytesIO()
            save_kwargs = {'format': format, 'optimize': True}
            
            if format == 'JPEG':
                save_kwargs['quality'] = quality
                save_kwargs['progressive'] = True
            elif format == 'PNG':
                save_kwargs['compress_level'] = 6
            
            image.save(output, **save_kwargs)
            
            return output.getvalue(), format.lower()
        
        except Exception as e:
            logger.error(f"图片优化失败: {e}")
            raise ValueError(f"图片处理失败: {str(e)}")
    
    @staticmethod
    def create_thumbnail(image_data: bytes, size: Tuple[int, int]) -> bytes:
        """创建缩略图"""
        try:
            image = Image.open(io.BytesIO(image_data))
            
            # 转换RGBA到RGB
            if image.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            
            # 自动旋转
            image = ImageOps.exif_transpose(image)
            
            # 创建缩略图（保持比例）
            image.thumbnail(size, Image.Resampling.LANCZOS)
            
            # 保存缩略图
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=80, optimize=True)
            
            return output.getvalue()
        
        except Exception as e:
            logger.error(f"缩略图创建失败: {e}")
            raise ValueError(f"缩略图创建失败: {str(e)}")

# 存储服务
class StorageService:
    """存储服务"""
    
    def __init__(self):
        self.client: Optional[Minio] = None
        self.initialized = False
    
    async def initialize(self):
        """初始化存储服务"""
        try:
            # 创建MinIO客户端
            self.client = Minio(
                endpoint=StorageConfig.MINIO_ENDPOINT,
                access_key=StorageConfig.MINIO_ACCESS_KEY,
                secret_key=StorageConfig.MINIO_SECRET_KEY,
                secure=StorageConfig.MINIO_SECURE,
                region=StorageConfig.MINIO_REGION
            )
            
            # 创建默认存储桶
            await self._ensure_buckets_exist()
            
            # 设置存储桶策略
            await self._setup_bucket_policies()
            
            self.initialized = True
            logger.info("存储服务初始化完成")
            
        except Exception as e:
            logger.error(f"初始化存储服务失败: {e}")
            raise
    
    async def _ensure_buckets_exist(self):
        """确保存储桶存在"""
        buckets = [
            StorageConfig.DEFAULT_BUCKET,
            StorageConfig.PUBLIC_BUCKET,
            StorageConfig.PRIVATE_BUCKET,
            StorageConfig.TEMP_BUCKET
        ]
        
        for bucket_name in buckets:
            try:
                if not self.client.bucket_exists(bucket_name):
                    self.client.make_bucket(bucket_name, location=StorageConfig.MINIO_REGION)
                    logger.info(f"创建存储桶: {bucket_name}")
            except S3Error as e:
                logger.error(f"创建存储桶失败 {bucket_name}: {e}")
                raise
    
    async def _setup_bucket_policies(self):
        """设置存储桶策略"""
        try:
            # 公开存储桶策略
            public_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": ["*"]},
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{StorageConfig.PUBLIC_BUCKET}/*"]
                    }
                ]
            }
            
            import json
            self.client.set_bucket_policy(
                StorageConfig.PUBLIC_BUCKET,
                json.dumps(public_policy)
            )
            
            logger.info(f"设置公开存储桶策略: {StorageConfig.PUBLIC_BUCKET}")
            
        except S3Error as e:
            logger.warning(f"设置存储桶策略失败: {e}")
    
    def _check_initialized(self):
        """检查是否已初始化"""
        if not self.initialized or not self.client:
            raise RuntimeError("存储服务未初始化")
    
    async def upload_file(
        self,
        file_data: bytes,
        upload_info: FileUpload,
        user_id: Optional[str] = None
    ) -> StorageResponse:
        """上传文件"""
        try:
            self._check_initialized()
            
            # 验证文件大小
            if len(file_data) > StorageConfig.MAX_FILE_SIZE:
                return StorageResponse(
                    success=False,
                    error=f"文件大小超过限制 ({StorageConfig.MAX_FILE_SIZE} 字节)"
                )
            
            # 验证文件类型
            if not is_allowed_file_type(upload_info.filename):
                return StorageResponse(
                    success=False,
                    error="不支持的文件类型"
                )
            
            # 清理文件名
            clean_filename = sanitize_filename(upload_info.filename)
            
            # 确定存储桶
            bucket = upload_info.bucket or (
                StorageConfig.PUBLIC_BUCKET if upload_info.is_public
                else StorageConfig.PRIVATE_BUCKET
            )
            
            # 生成存储路径
            if upload_info.path:
                storage_path = upload_info.path
            else:
                storage_path = generate_storage_path(
                    user_id or "anonymous",
                    clean_filename,
                    upload_info.is_public
                )
            
            # 确定内容类型
            content_type = upload_info.content_type or get_content_type(clean_filename)
            
            # 计算校验和
            checksum = calculate_checksum(file_data)
            
            # 准备元数据
            metadata = {
                'original-filename': upload_info.filename,
                'upload-user': user_id or "anonymous",
                'upload-time': datetime.now(timezone.utc).isoformat(),
                'checksum': checksum,
                **(upload_info.metadata or {})
            }
            
            # 上传文件
            self.client.put_object(
                bucket_name=bucket,
                object_name=storage_path,
                data=io.BytesIO(file_data),
                length=len(file_data),
                content_type=content_type,
                metadata=metadata
            )
            
            # 生成文件信息
            file_info = FileInfo(
                id=generate_file_id(),
                filename=clean_filename,
                original_filename=upload_info.filename,
                content_type=content_type,
                size=len(file_data),
                bucket=bucket,
                path=storage_path,
                is_public=upload_info.is_public,
                metadata=metadata,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                checksum=checksum
            )
            
            # 生成URL
            if upload_info.is_public:
                file_info.public_url = f"{StorageConfig.PUBLIC_URL_BASE}/{bucket}/{storage_path}"
                file_info.url = file_info.public_url
            else:
                file_info.url = self.client.presigned_get_object(
                    bucket_name=bucket,
                    object_name=storage_path,
                    expires=timedelta(seconds=StorageConfig.SIGNED_URL_EXPIRE_SECONDS)
                )
            
            return StorageResponse(
                success=True,
                message="文件上传成功",
                file_info=file_info,
                url=file_info.url
            )
        
        except Exception as e:
            logger.error(f"文件上传失败: {e}")
            return StorageResponse(
                success=False,
                error=f"文件上传失败: {str(e)}"
            )
    
    async def upload_image(
        self,
        image_data: bytes,
        upload_info: ImageUpload,
        user_id: Optional[str] = None
    ) -> StorageResponse:
        """上传图片"""
        try:
            self._check_initialized()
            
            # 验证图片大小
            if len(image_data) > StorageConfig.MAX_IMAGE_SIZE:
                return StorageResponse(
                    success=False,
                    error=f"图片大小超过限制 ({StorageConfig.MAX_IMAGE_SIZE} 字节)"
                )
            
            # 验证图片类型
            if not is_image(upload_info.filename):
                return StorageResponse(
                    success=False,
                    error="不支持的图片类型"
                )
            
            # 优化图片
            try:
                optimized_data, output_format = ImageProcessor.optimize_image(
                    image_data,
                    max_size=upload_info.resize,
                    quality=upload_info.quality or StorageConfig.IMAGE_QUALITY,
                    format=upload_info.format
                )
            except ValueError as e:
                return StorageResponse(
                    success=False,
                    error=str(e)
                )
            
            # 更新文件名扩展名
            name_without_ext = os.path.splitext(upload_info.filename)[0]
            optimized_filename = f"{name_without_ext}.{output_format}"
            
            # 创建文件上传信息
            file_upload = FileUpload(
                filename=optimized_filename,
                content_type=f"image/{output_format}",
                bucket=upload_info.bucket,
                path=upload_info.path,
                is_public=upload_info.is_public,
                metadata=upload_info.metadata
            )
            
            # 上传主图片
            response = await self.upload_file(optimized_data, file_upload, user_id)
            
            if not response.success:
                return response
            
            # 创建缩略图
            thumbnails = []
            if upload_info.create_thumbnails:
                for size in StorageConfig.THUMBNAIL_SIZES:
                    try:
                        thumbnail_data = ImageProcessor.create_thumbnail(optimized_data, size)
                        
                        # 生成缩略图路径
                        base_path = os.path.splitext(response.file_info.path)[0]
                        thumbnail_path = f"{base_path}_thumb_{size[0]}x{size[1]}.jpg"
                        
                        # 上传缩略图
                        thumbnail_upload = FileUpload(
                            filename=f"thumbnail_{size[0]}x{size[1]}.jpg",
                            content_type="image/jpeg",
                            bucket=response.file_info.bucket,
                            path=thumbnail_path,
                            is_public=upload_info.is_public
                        )
                        
                        thumbnail_response = await self.upload_file(
                            thumbnail_data,
                            thumbnail_upload,
                            user_id
                        )
                        
                        if thumbnail_response.success:
                            thumbnails.append(thumbnail_response.file_info.url)
                    
                    except Exception as e:
                        logger.warning(f"创建缩略图失败 {size}: {e}")
            
            # 更新文件信息
            response.file_info.thumbnails = thumbnails if thumbnails else None
            
            return response
        
        except Exception as e:
            logger.error(f"图片上传失败: {e}")
            return StorageResponse(
                success=False,
                error=f"图片上传失败: {str(e)}"
            )
    
    async def download_file(self, bucket: str, path: str) -> Tuple[Optional[bytes], Optional[str]]:
        """下载文件"""
        try:
            self._check_initialized()
            
            # 获取文件对象
            response = self.client.get_object(bucket, path)
            
            # 读取文件数据
            file_data = response.read()
            
            # 获取内容类型
            content_type = response.headers.get('Content-Type', 'application/octet-stream')
            
            response.close()
            response.release_conn()
            
            return file_data, content_type
        
        except S3Error as e:
            if e.code == 'NoSuchKey':
                logger.warning(f"文件不存在: {bucket}/{path}")
                return None, None
            else:
                logger.error(f"下载文件失败: {e}")
                raise
        except Exception as e:
            logger.error(f"下载文件失败: {e}")
            raise
    
    async def delete_file(self, bucket: str, path: str) -> StorageResponse:
        """删除文件"""
        try:
            self._check_initialized()
            
            # 删除文件
            self.client.remove_object(bucket, path)
            
            return StorageResponse(
                success=True,
                message="文件删除成功"
            )
        
        except S3Error as e:
            if e.code == 'NoSuchKey':
                return StorageResponse(
                    success=False,
                    error="文件不存在"
                )
            else:
                logger.error(f"删除文件失败: {e}")
                return StorageResponse(
                    success=False,
                    error=f"删除文件失败: {str(e)}"
                )
        except Exception as e:
            logger.error(f"删除文件失败: {e}")
            return StorageResponse(
                success=False,
                error=f"删除文件失败: {str(e)}"
            )
    
    async def get_file_info(self, bucket: str, path: str) -> Optional[FileInfo]:
        """获取文件信息"""
        try:
            self._check_initialized()
            
            # 获取文件统计信息
            stat = self.client.stat_object(bucket, path)
            
            # 构建文件信息
            file_info = FileInfo(
                id=generate_file_id(),
                filename=os.path.basename(path),
                original_filename=stat.metadata.get('original-filename', os.path.basename(path)),
                content_type=stat.content_type,
                size=stat.size,
                bucket=bucket,
                path=path,
                is_public=bucket == StorageConfig.PUBLIC_BUCKET,
                metadata=dict(stat.metadata) if stat.metadata else None,
                created_at=stat.last_modified,
                updated_at=stat.last_modified,
                checksum=stat.metadata.get('checksum') if stat.metadata else None
            )
            
            # 生成URL
            if file_info.is_public:
                file_info.public_url = f"{StorageConfig.PUBLIC_URL_BASE}/{bucket}/{path}"
                file_info.url = file_info.public_url
            else:
                file_info.url = self.client.presigned_get_object(
                    bucket_name=bucket,
                    object_name=path,
                    expires=timedelta(seconds=StorageConfig.SIGNED_URL_EXPIRE_SECONDS)
                )
            
            return file_info
        
        except S3Error as e:
            if e.code == 'NoSuchKey':
                return None
            else:
                logger.error(f"获取文件信息失败: {e}")
                raise
        except Exception as e:
            logger.error(f"获取文件信息失败: {e}")
            raise
    
    async def list_files(
        self,
        bucket: str,
        prefix: Optional[str] = None,
        limit: Optional[int] = None
    ) -> StorageResponse:
        """列出文件"""
        try:
            self._check_initialized()
            
            # 列出对象
            objects = self.client.list_objects(
                bucket_name=bucket,
                prefix=prefix,
                recursive=True
            )
            
            files = []
            count = 0
            
            for obj in objects:
                if limit and count >= limit:
                    break
                
                # 获取文件信息
                file_info = await self.get_file_info(bucket, obj.object_name)
                if file_info:
                    files.append(file_info)
                    count += 1
            
            return StorageResponse(
                success=True,
                files=files,
                message=f"找到 {len(files)} 个文件"
            )
        
        except Exception as e:
            logger.error(f"列出文件失败: {e}")
            return StorageResponse(
                success=False,
                error=f"列出文件失败: {str(e)}"
            )
    
    async def generate_signed_url(
        self,
        bucket: str,
        path: str,
        expires_in: Optional[int] = None,
        method: str = "GET"
    ) -> StorageResponse:
        """生成签名URL"""
        try:
            self._check_initialized()
            
            expires = timedelta(seconds=expires_in or StorageConfig.SIGNED_URL_EXPIRE_SECONDS)
            
            if method.upper() == "GET":
                url = self.client.presigned_get_object(
                    bucket_name=bucket,
                    object_name=path,
                    expires=expires
                )
            elif method.upper() == "PUT":
                url = self.client.presigned_put_object(
                    bucket_name=bucket,
                    object_name=path,
                    expires=expires
                )
            else:
                return StorageResponse(
                    success=False,
                    error=f"不支持的HTTP方法: {method}"
                )
            
            return StorageResponse(
                success=True,
                url=url,
                message="签名URL生成成功"
            )
        
        except Exception as e:
            logger.error(f"生成签名URL失败: {e}")
            return StorageResponse(
                success=False,
                error=f"生成签名URL失败: {str(e)}"
            )
    
    async def copy_file(
        self,
        source_bucket: str,
        source_path: str,
        dest_bucket: str,
        dest_path: str
    ) -> StorageResponse:
        """复制文件"""
        try:
            self._check_initialized()
            
            from minio.commonconfig import CopySource
            
            # 复制文件
            self.client.copy_object(
                bucket_name=dest_bucket,
                object_name=dest_path,
                source=CopySource(source_bucket, source_path)
            )
            
            return StorageResponse(
                success=True,
                message="文件复制成功"
            )
        
        except Exception as e:
            logger.error(f"复制文件失败: {e}")
            return StorageResponse(
                success=False,
                error=f"复制文件失败: {str(e)}"
            )
    
    async def get_bucket_info(self, bucket_name: str) -> Optional[BucketInfo]:
        """获取存储桶信息"""
        try:
            self._check_initialized()
            
            # 检查存储桶是否存在
            if not self.client.bucket_exists(bucket_name):
                return None
            
            # 获取存储桶列表（包含创建时间）
            buckets = self.client.list_buckets()
            bucket_data = next((b for b in buckets if b.name == bucket_name), None)
            
            if not bucket_data:
                return None
            
            # 计算存储桶大小和对象数量
            total_size = 0
            object_count = 0
            
            objects = self.client.list_objects(bucket_name, recursive=True)
            for obj in objects:
                total_size += obj.size
                object_count += 1
            
            return BucketInfo(
                name=bucket_name,
                creation_date=bucket_data.creation_date,
                is_public=bucket_name == StorageConfig.PUBLIC_BUCKET,
                size=total_size,
                object_count=object_count
            )
        
        except Exception as e:
            logger.error(f"获取存储桶信息失败: {e}")
            return None
    
    async def cleanup_temp_files(self):
        """清理临时文件"""
        try:
            self._check_initialized()
            
            # 获取过期时间
            expire_time = datetime.now(timezone.utc) - timedelta(hours=StorageConfig.TEMP_FILE_EXPIRE_HOURS)
            
            # 列出临时文件
            objects = self.client.list_objects(
                bucket_name=StorageConfig.TEMP_BUCKET,
                recursive=True
            )
            
            deleted_count = 0
            
            for obj in objects:
                if obj.last_modified < expire_time:
                    try:
                        self.client.remove_object(StorageConfig.TEMP_BUCKET, obj.object_name)
                        deleted_count += 1
                    except Exception as e:
                        logger.warning(f"删除临时文件失败 {obj.object_name}: {e}")
            
            logger.info(f"清理了 {deleted_count} 个临时文件")
            
        except Exception as e:
            logger.error(f"清理临时文件失败: {e}")

# 全局存储服务实例
storage_service = StorageService()

# 兼容性函数（替代原有的Supabase存储）
async def upload_base64_image(
    base64_data: str,
    bucket: str = "images",
    filename: Optional[str] = None,
    user_id: Optional[str] = None
) -> str:
    """上传base64图片（兼容性函数）"""
    import base64
    
    try:
        # 解码base64数据
        if ',' in base64_data:
            header, data = base64_data.split(',', 1)
        else:
            data = base64_data
        
        image_data = base64.b64decode(data)
        
        # 生成文件名
        if not filename:
            filename = f"image_{generate_file_id()}.jpg"
        
        # 创建图片上传信息
        upload_info = ImageUpload(
            filename=filename,
            bucket=bucket,
            is_public=True,
            create_thumbnails=True
        )
        
        # 上传图片
        response = await storage_service.upload_image(image_data, upload_info, user_id)
        
        if response.success:
            return response.file_info.url
        else:
            raise Exception(response.error)
    
    except Exception as e:
        logger.error(f"上传base64图片失败: {e}")
        raise

class StorageClient:
    """存储客户端（兼容性包装器）"""
    
    def __init__(self):
        self.service = storage_service
    
    async def upload(self, bucket: str, path: str, file_data: bytes, **kwargs) -> Dict[str, Any]:
        """上传文件"""
        upload_info = FileUpload(
            filename=os.path.basename(path),
            bucket=bucket,
            path=path,
            is_public=kwargs.get('is_public', False),
            metadata=kwargs.get('metadata')
        )
        
        response = await self.service.upload_file(file_data, upload_info)
        
        if response.success:
            return {
                "data": {
                    "path": response.file_info.path,
                    "fullPath": response.file_info.path,
                    "id": response.file_info.id
                },
                "error": None
            }
        else:
            return {
                "data": None,
                "error": {"message": response.error}
            }
    
    async def download(self, bucket: str, path: str) -> Dict[str, Any]:
        """下载文件"""
        try:
            file_data, content_type = await self.service.download_file(bucket, path)
            
            if file_data:
                return {
                    "data": file_data,
                    "error": None
                }
            else:
                return {
                    "data": None,
                    "error": {"message": "文件不存在"}
                }
        
        except Exception as e:
            return {
                "data": None,
                "error": {"message": str(e)}
            }
    
    async def remove(self, bucket: str, paths: List[str]) -> Dict[str, Any]:
        """删除文件"""
        try:
            for path in paths:
                await self.service.delete_file(bucket, path)
            
            return {
                "data": {"message": "文件删除成功"},
                "error": None
            }
        
        except Exception as e:
            return {
                "data": None,
                "error": {"message": str(e)}
            }
    
    def get_public_url(self, bucket: str, path: str) -> str:
        """获取公开URL"""
        return f"{StorageConfig.PUBLIC_URL_BASE}/{bucket}/{path}"
    
    async def create_signed_url(
        self,
        bucket: str,
        path: str,
        expires_in: int = 3600
    ) -> Dict[str, Any]:
        """创建签名URL"""
        response = await self.service.generate_signed_url(bucket, path, expires_in)
        
        if response.success:
            return {
                "data": {"signedUrl": response.url},
                "error": None
            }
        else:
            return {
                "data": None,
                "error": {"message": response.error}
            }

# 创建存储客户端实例
def create_storage_client() -> StorageClient:
    """创建存储客户端"""
    return StorageClient()