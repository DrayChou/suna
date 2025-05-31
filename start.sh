#!/bin/bash

# Suna 开源版本 - 快速启动脚本
# 适用于 Linux 和 macOS

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}[信息]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[成功]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[警告]${NC} $1"
}

print_error() {
    echo -e "${RED}[错误]${NC} $1"
}

# 检查命令是否存在
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 主函数
main() {
    echo "========================================"
    echo "    Suna 开源版本 - 快速启动脚本"
    echo "========================================"
    echo
    
    # 检查Python环境
    print_info "检查Python环境..."
    if ! command_exists python3; then
        if ! command_exists python; then
            print_error "未找到Python，请先安装Python 3.9+"
            exit 1
        else
            PYTHON_CMD="python"
        fi
    else
        PYTHON_CMD="python3"
    fi
    
    # 检查Python版本
    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
    REQUIRED_VERSION="3.9"
    
    if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
        print_error "Python版本过低，需要3.9+，当前版本：$PYTHON_VERSION"
        exit 1
    fi
    
    print_success "Python环境检查通过 (版本: $PYTHON_VERSION)"
    
    # 检查Docker环境
    print_info "检查Docker环境..."
    if ! command_exists docker; then
        print_error "未找到Docker，请先安装Docker"
        exit 1
    fi
    
    # 检查Docker是否运行
    if ! docker info >/dev/null 2>&1; then
        print_error "Docker未运行，请启动Docker服务"
        exit 1
    fi
    
    print_success "Docker环境检查通过"
    
    # 检查Docker Compose
    print_info "检查Docker Compose..."
    if ! command_exists docker-compose; then
        print_error "未找到Docker Compose，请先安装Docker Compose"
        exit 1
    fi
    
    print_success "Docker Compose检查通过"
    
    echo
    print_success "环境检查通过！"
    echo
    
    # 检查必要文件
    print_info "检查必要文件..."
    
    if [ ! -f "scripts/requirements.txt" ]; then
        print_error "找不到scripts/requirements.txt文件"
        exit 1
    fi
    
    if [ ! -f "docker-compose.opensource.yml" ]; then
        print_error "找不到docker-compose.opensource.yml文件"
        exit 1
    fi
    
    if [ ! -f ".env.opensource" ]; then
        print_error "找不到.env.opensource文件"
        exit 1
    fi
    
    print_success "必要文件检查通过"
    
    # 安装Python依赖
    print_info "安装Python依赖..."
    
    if ! $PYTHON_CMD -m pip install -r scripts/requirements.txt; then
        print_error "安装启动脚本依赖失败"
        exit 1
    fi
    
    print_success "Python依赖安装完成"
    
    echo
    print_info "启动Suna开源版本..."
    echo
    
    # 启动服务
    $PYTHON_CMD scripts/start-opensource.py start
}

# 信号处理
trap 'echo; print_warning "收到中断信号，正在退出..."; exit 130' INT TERM

# 检查是否在正确的目录
if [ ! -f "scripts/start-opensource.py" ]; then
    print_error "请在Suna项目根目录下运行此脚本"
    exit 1
fi

# 运行主函数
main "$@"