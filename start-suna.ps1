#!/usr/bin/env pwsh
# Suna 服务启动脚本
# 用于启动分离后的基础服务和应用服务

Write-Host "=== Suna 服务管理脚本 ===" -ForegroundColor Green
Write-Host ""

# 检查 Docker 是否运行
try {
    docker version | Out-Null
    Write-Host "✓ Docker 服务正在运行" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker 服务未运行，请先启动 Docker" -ForegroundColor Red
    exit 1
}

# 函数：启动基础服务
function Start-BaseServices {
    Write-Host "启动基础服务..." -ForegroundColor Yellow
    docker-compose -f docker-compose.base.yml --env-file .env.opensource up -d
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ 基础服务启动成功" -ForegroundColor Green
    } else {
        Write-Host "✗ 基础服务启动失败" -ForegroundColor Red
        return $false
    }
    return $true
}

# 函数：启动应用服务
function Start-AppServices {
    Write-Host "启动应用服务..." -ForegroundColor Yellow
    docker-compose -f docker-compose.apps.yml --env-file .env.opensource up -d
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ 应用服务启动成功" -ForegroundColor Green
    } else {
        Write-Host "✗ 应用服务启动失败" -ForegroundColor Red
        return $false
    }
    return $true
}

# 函数：停止所有服务
function Stop-AllServices {
    Write-Host "停止所有 Suna 服务..." -ForegroundColor Yellow
    docker-compose -f docker-compose.apps.yml --env-file .env.opensource down
    docker-compose -f docker-compose.base.yml --env-file .env.opensource down
    Write-Host "✓ 所有服务已停止" -ForegroundColor Green
}

# 函数：显示服务状态
function Show-ServiceStatus {
    Write-Host "Suna 服务状态:" -ForegroundColor Cyan
    docker ps --filter 'name=suna' --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
}

# 函数：显示服务日志
function Show-ServiceLogs {
    param([string]$ServiceName)
    if ($ServiceName) {
        docker logs -f $ServiceName
    } else {
        Write-Host "请指定服务名称，例如: suna-backend, suna-postgres 等" -ForegroundColor Yellow
        Show-ServiceStatus
    }
}

# 主菜单
function Show-Menu {
    Write-Host ""
    Write-Host "请选择操作:" -ForegroundColor Cyan
    Write-Host "1. 启动基础服务 (数据库、缓存、消息队列等)"
    Write-Host "2. 启动应用服务 (后端、前端、工作进程等)"
    Write-Host "3. 启动所有服务"
    Write-Host "4. 停止所有服务"
    Write-Host "5. 查看服务状态"
    Write-Host "6. 查看服务日志"
    Write-Host "7. 退出"
    Write-Host ""
}

# 主循环
while ($true) {
    Show-Menu
    $choice = Read-Host "请输入选择 (1-7)"
    
    switch ($choice) {
        "1" {
            Start-BaseServices
        }
        "2" {
            Start-AppServices
        }
        "3" {
            if (Start-BaseServices) {
                Start-Sleep -Seconds 5  # 等待基础服务完全启动
                Start-AppServices
            }
        }
        "4" {
            Stop-AllServices
        }
        "5" {
            Show-ServiceStatus
        }
        "6" {
            $serviceName = Read-Host "请输入服务名称 (留空显示所有服务)"
            if ($serviceName) {
                Show-ServiceLogs $serviceName
            } else {
                Show-ServiceStatus
            }
        }
        "7" {
            Write-Host "再见!" -ForegroundColor Green
            break
        }
        default {
            Write-Host "无效选择，请输入 1-7" -ForegroundColor Red
        }
    }
    
    if ($choice -ne "6" -and $choice -ne "7") {
        Write-Host ""
        Read-Host "按回车键继续..."
        Clear-Host
        Write-Host "=== Suna 服务管理脚本 ===" -ForegroundColor Green
    }
}