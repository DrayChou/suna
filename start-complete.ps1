#!/usr/bin/env pwsh
# Suna 完整启动脚本
# 包含后端Docker服务和前端Next.js应用的完整启动流程
# 作者: DR (博士)

# 设置控制台编码为UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "========================================" -ForegroundColor Green
Write-Host "    Suna 完整启动脚本 v1.0" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# 全局变量
$script:BackendStarted = $false
$script:FrontendStarted = $false
$script:FrontendProcess = $null

# 函数：检查必要的环境
function Test-Prerequisites {
    Write-Host "检查运行环境..." -ForegroundColor Yellow
    
    # 检查Docker
    try {
        docker version | Out-Null
        Write-Host "✓ Docker 服务正在运行" -ForegroundColor Green
    } catch {
        Write-Host "✗ Docker 服务未运行，请先启动 Docker Desktop" -ForegroundColor Red
        return $false
    }
    
    # 检查Node.js
    try {
        node --version | Out-Null
        Write-Host "✓ Node.js 已安装" -ForegroundColor Green
    } catch {
        Write-Host "✗ 未找到 Node.js，请先安装 Node.js" -ForegroundColor Red
        return $false
    }
    
    # 检查npm
    try {
        npm --version | Out-Null
        Write-Host "✓ npm 已安装" -ForegroundColor Green
    } catch {
        Write-Host "✗ 未找到 npm" -ForegroundColor Red
        return $false
    }
    
    Write-Host "✓ 环境检查通过" -ForegroundColor Green
    return $true
}

# 函数：启动后端Docker服务
function Start-BackendServices {
    Write-Host "" 
    Write-Host "启动后端Docker服务..." -ForegroundColor Yellow
    
    # 检查是否已有运行的容器
    $runningContainers = docker ps --filter "name=suna" --format "{{.Names}}"
    if ($runningContainers) {
        Write-Host "检测到已运行的Suna容器:" -ForegroundColor Cyan
        $runningContainers | ForEach-Object { Write-Host "  - $_" -ForegroundColor White }
        $restart = Read-Host "是否重启所有服务? (y/N)"
        if ($restart -eq 'y' -or $restart -eq 'Y') {
            Stop-BackendServices
        } else {
            Write-Host "✓ 使用现有的后端服务" -ForegroundColor Green
            $script:BackendStarted = $true
            return $true
        }
    }
    
    try {
        # 启动所有Docker服务
        Write-Host "正在启动Docker Compose服务..." -ForegroundColor Cyan
        docker-compose up -d
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Docker服务启动命令执行成功" -ForegroundColor Green
            
            # 等待服务启动
            Write-Host "等待服务完全启动..." -ForegroundColor Cyan
            Start-Sleep -Seconds 15
            
            # 检查服务状态
            Show-BackendStatus
            $script:BackendStarted = $true
            return $true
        } else {
            Write-Host "✗ Docker服务启动失败" -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host "✗ 启动Docker服务时发生错误: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

# 函数：停止后端服务
function Stop-BackendServices {
    Write-Host "停止后端Docker服务..." -ForegroundColor Yellow
    try {
        docker-compose down
        Write-Host "✓ 后端服务已停止" -ForegroundColor Green
        $script:BackendStarted = $false
    } catch {
        Write-Host "✗ 停止后端服务时发生错误" -ForegroundColor Red
    }
}

# 函数：显示后端服务状态
function Show-BackendStatus {
    Write-Host "" 
    Write-Host "后端服务状态:" -ForegroundColor Cyan
    docker ps --filter "name=suna" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    Write-Host ""
}

# 函数：准备前端环境
function Initialize-Frontend {
    Write-Host "准备前端环境..." -ForegroundColor Yellow
    
    # 切换到前端目录
    Push-Location "frontend"
    
    try {
        # 检查.env文件
        if (-not (Test-Path ".env")) {
            Write-Host "创建前端环境配置文件..." -ForegroundColor Cyan
            if (Test-Path ".env.example") {
                Copy-Item ".env.example" ".env"
                Write-Host "✓ 已从.env.example创建.env文件" -ForegroundColor Green
            } else {
                Write-Host "✗ 未找到.env.example文件" -ForegroundColor Red
                return $false
            }
        }
        
        # 检查node_modules
        if (-not (Test-Path "node_modules")) {
            Write-Host "安装前端依赖..." -ForegroundColor Cyan
            
            # 清理npm缓存并设置registry
            npm cache clean --force
            npm config set registry https://registry.npmjs.org/
            
            npm install
            if ($LASTEXITCODE -ne 0) {
                Write-Host "✗ 前端依赖安装失败" -ForegroundColor Red
                return $false
            }
            Write-Host "✓ 前端依赖安装完成" -ForegroundColor Green
        } else {
            Write-Host "✓ 前端依赖已存在" -ForegroundColor Green
        }
        
        return $true
    } catch {
        Write-Host "✗ 准备前端环境时发生错误: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    } finally {
        Pop-Location
    }
}

# 函数：启动前端服务
function Start-FrontendService {
    Write-Host "" 
    Write-Host "启动前端开发服务器..." -ForegroundColor Yellow
    
    # 检查前端是否已在运行
    $frontendPort = netstat -an | Select-String ":15014.*LISTENING"
    if ($frontendPort) {
        Write-Host "检测到3000端口已被占用，前端服务可能已在运行" -ForegroundColor Cyan
        $restart = Read-Host "是否重启前端服务? (y/N)"
        if ($restart -eq 'y' -or $restart -eq 'Y') {
            Stop-FrontendService
        } else {
            Write-Host "✓ 使用现有的前端服务" -ForegroundColor Green
            $script:FrontendStarted = $true
            return $true
        }
    }
    
    # 初始化前端环境
    if (-not (Initialize-Frontend)) {
        return $false
    }
    
    try {
        # 切换到前端目录并启动开发服务器
        Push-Location "frontend"
        
        Write-Host "正在启动Next.js开发服务器..." -ForegroundColor Cyan
        $script:FrontendProcess = Start-Process -FilePath "npm" -ArgumentList "run", "dev" -NoNewWindow -PassThru
        
        # 等待前端服务启动
        Write-Host "等待前端服务启动..." -ForegroundColor Cyan
        $timeout = 30
        $elapsed = 0
        
        do {
            Start-Sleep -Seconds 2
            $elapsed += 2
            $frontendRunning = netstat -an | Select-String ":15014.*LISTENING"
        } while (-not $frontendRunning -and $elapsed -lt $timeout)
        
        if ($frontendRunning) {
            Write-Host "✓ 前端服务启动成功" -ForegroundColor Green
            $script:FrontendStarted = $true
            return $true
        } else {
            Write-Host "✗ 前端服务启动超时" -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host "✗ 启动前端服务时发生错误: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    } finally {
        Pop-Location
    }
}

# 函数：停止前端服务
function Stop-FrontendService {
    Write-Host "停止前端服务..." -ForegroundColor Yellow
    
    if ($script:FrontendProcess -and -not $script:FrontendProcess.HasExited) {
        try {
            $script:FrontendProcess.Kill()
            Write-Host "✓ 前端服务进程已终止" -ForegroundColor Green
        } catch {
            Write-Host "✗ 终止前端服务进程失败" -ForegroundColor Red
        }
    }
    
    # 查找并终止占用15014端口的进程
    $processes = netstat -ano | Select-String ":15014.*LISTENING" | ForEach-Object {
        ($_ -split "\s+")[-1]
    }
    
    foreach ($processId in $processes) {
        try {
            Stop-Process -Id $processId -Force
            Write-Host "✓ 已终止PID为$processId的进程" -ForegroundColor Green
        } catch {
            Write-Host "✗ 无法终止PID为$processId的进程" -ForegroundColor Red
        }
    }
    
    $script:FrontendStarted = $false
    $script:FrontendProcess = $null
}

# 函数：显示服务访问地址
function Show-AccessUrls {
    Write-Host "" 
    Write-Host "=== 服务访问地址 ===" -ForegroundColor Green
    if ($script:BackendStarted) {
        Write-Host "后端API:      http://localhost:15013" -ForegroundColor White
        Write-Host "认证服务:     http://localhost:15002" -ForegroundColor White
        Write-Host "数据库管理:   http://localhost:15001" -ForegroundColor White
    }
    if ($script:FrontendStarted) {
        Write-Host "前端界面:     http://localhost:15014" -ForegroundColor White
    }
    Write-Host "" 
}

# 函数：显示完整状态
function Show-CompleteStatus {
    Write-Host "" 
    Write-Host "=== Suna 系统状态 ===" -ForegroundColor Cyan
    
    if ($script:BackendStarted) {
        Write-Host "后端服务: " -NoNewline
        Write-Host "运行中" -ForegroundColor Green
        Show-BackendStatus
    } else {
        Write-Host "后端服务: " -NoNewline
        Write-Host "未启动" -ForegroundColor Red
    }
    
    if ($script:FrontendStarted) {
        Write-Host "前端服务: " -NoNewline
        Write-Host "运行中" -ForegroundColor Green
        $frontendPort = netstat -an | Select-String ":15014.*LISTENING"
        if ($frontendPort) {
            Write-Host "  - 监听端口: 15014" -ForegroundColor White
        }
    } else {
        Write-Host "前端服务: " -NoNewline
        Write-Host "未启动" -ForegroundColor Red
    }
    
    Show-AccessUrls
}

# 函数：启动所有服务
function Start-AllServices {
    Write-Host "启动完整的Suna系统..." -ForegroundColor Green
    Write-Host "" 
    
    # 启动后端服务
    if (-not (Start-BackendServices)) {
        Write-Host "✗ 后端服务启动失败，停止启动流程" -ForegroundColor Red
        return $false
    }
    
    # 启动前端服务
    if (-not (Start-FrontendService)) {
        Write-Host "✗ 前端服务启动失败" -ForegroundColor Red
        return $false
    }
    
    Write-Host "" 
    Write-Host "🎉 Suna系统启动完成！" -ForegroundColor Green
    Show-AccessUrls
    
    return $true
}

# 函数：停止所有服务
function Stop-AllServices {
    Write-Host "停止所有Suna服务..." -ForegroundColor Yellow
    
    Stop-FrontendService
    Stop-BackendServices
    
    Write-Host "✓ 所有服务已停止" -ForegroundColor Green
}

# 函数：显示主菜单
function Show-MainMenu {
    Write-Host "" 
    Write-Host "请选择操作:" -ForegroundColor Cyan
    Write-Host "1. 启动所有服务 (推荐)" -ForegroundColor White
    Write-Host "2. 仅启动后端服务" -ForegroundColor White
    Write-Host "3. 仅启动前端服务" -ForegroundColor White
    Write-Host "4. 停止所有服务" -ForegroundColor White
    Write-Host "5. 查看服务状态" -ForegroundColor White
    Write-Host "6. 查看访问地址" -ForegroundColor White
    Write-Host "7. 查看后端日志" -ForegroundColor White
    Write-Host "8. 重启所有服务" -ForegroundColor White
    Write-Host "9. 退出" -ForegroundColor White
    Write-Host "" 
}

# 函数：查看后端日志
function Show-BackendLogs {
    Write-Host "" 
    Write-Host "可用的后端服务:" -ForegroundColor Cyan
    $services = docker ps --filter "name=suna" --format "{{.Names}}"
    if ($services) {
        $services | ForEach-Object { Write-Host "  - $_" -ForegroundColor White }
        Write-Host "" 
        $serviceName = Read-Host "请输入要查看日志的服务名称 (留空返回主菜单)"
        if ($serviceName) {
            Write-Host "正在显示 $serviceName 的日志 (按 Ctrl+C 退出):" -ForegroundColor Yellow
            docker logs -f $serviceName
        }
    } else {
        Write-Host "  没有运行中的后端服务" -ForegroundColor Red
    }
}

# 主程序入口
function Main {
    # 检查环境
    if (-not (Test-Prerequisites)) {
        Write-Host "" 
        Write-Host "请解决环境问题后重新运行脚本" -ForegroundColor Red
        Read-Host "按回车键退出"
        exit 1
    }
    
    # 主循环
    while ($true) {
        Show-MainMenu
        $choice = Read-Host "请输入选择 (1-9)"
        
        switch ($choice) {
            "1" {
                Start-AllServices
            }
            "2" {
                Start-BackendServices
            }
            "3" {
                Start-FrontendService
            }
            "4" {
                Stop-AllServices
            }
            "5" {
                Show-CompleteStatus
            }
            "6" {
                Show-AccessUrls
            }
            "7" {
                Show-BackendLogs
            }
            "8" {
                Write-Host "重启所有服务..." -ForegroundColor Yellow
                Stop-AllServices
                Start-Sleep -Seconds 3
                Start-AllServices
            }
            "9" {
                Write-Host "" 
                Write-Host "感谢使用Suna启动脚本！" -ForegroundColor Green
                if ($script:FrontendStarted -or $script:BackendStarted) {
                    $stopServices = Read-Host "是否在退出前停止所有服务? (Y/n)"
                    if ($stopServices -ne 'n' -and $stopServices -ne 'N') {
                        Stop-AllServices
                    }
                }
                Write-Host "再见！" -ForegroundColor Green
                break
            }
            default {
                Write-Host "无效选择，请输入 1-9" -ForegroundColor Red
            }
        }
        
        if ($choice -ne "7" -and $choice -ne "9") {
            Write-Host "" 
            Read-Host "按回车键继续..."
            Clear-Host
            Write-Host "========================================" -ForegroundColor Green
            Write-Host "    Suna 完整启动脚本 v1.0" -ForegroundColor Green
            Write-Host "========================================" -ForegroundColor Green
        }
    }
}

# 脚本清理函数
function Cleanup {
    if ($script:FrontendProcess -and -not $script:FrontendProcess.HasExited) {
        Write-Host "清理前端进程..." -ForegroundColor Yellow
        try {
            $script:FrontendProcess.Kill()
        } catch {
            # 忽略清理错误
        }
    }
}

# 注册清理函数
Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action { Cleanup }

# 启动主程序
try {
    Main
} catch {
    Write-Host "脚本执行过程中发生错误: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "堆栈跟踪: $($_.ScriptStackTrace)" -ForegroundColor Red
} finally {
    Cleanup
}