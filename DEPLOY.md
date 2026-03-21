# Youtu-Agent 一键部署指南

## 快速开始

### 初次部署步骤

1. **配置环境文件**（必须）：
```bash
# 复制配置模板
cp docker/.env.docker.example docker/.env

# 编辑配置文件，设置您的API密钥
nano docker/.env
```

2. **运行部署脚本**：
```bash
# 使用本地代码构建（推荐）
./deploy.sh

# 或从 GitHub 拉取最新代码构建
./deploy.sh --mode github
```

### 日常使用

```bash
# 1. 使用本地代码构建（默认）
./deploy.sh

# 2. 从GitHub拉取最新代码构建
./deploy.sh --mode github

# 3. 后台运行模式
./deploy.sh --detach

# 4. 强制重启Phoenix容器
./deploy.sh --phoenix

# 5. 清理旧容器后重新部署
./deploy.sh --clean
```

### 组合使用

```bash
# 从GitHub构建，清理旧容器，后台运行
./deploy.sh -m github -c -d

# 强制重启Phoenix，使用本地代码，前台运行
./deploy.sh -p -m local

# 仅删除容器和镜像，不重新构建
./deploy.sh --remove
```

## 部署选项

| 选项 | 短选项 | 描述 | 默认值 |
|------|--------|------|--------|
| `--mode` | `-m` | 构建模式 (`local`/`github`) | `local` |
| `--phoenix` | `-p` | 强制重启Phoenix容器 | `false` |
| `--clean` | `-c` | 清理旧容器和镜像 | `false` |
| `--remove` | `-r` | 删除旧容器和镜像，不重新构建 | `false` |
| `--detach` | `-d` | 后台运行模式 | `false` |
| `--help` | `-h` | 显示帮助信息 | - |

## 构建模式说明

### Local模式（推荐开发使用）
- 使用当前目录的代码进行构建
- 适合本地开发和测试
- 修改代码后需要重新构建

### GitHub模式
- 从官方GitHub仓库拉取最新代码
- 适合生产部署
- 确保使用最新稳定版本

## 服务访问

部署成功后，您可以通过以下地址访问服务：

- **Youtu-Agent WebUI**: http://localhost:8848
- **Phoenix追踪面板**: http://localhost:6006

## 环境配置

### 必要的配置步骤

**重要**: 在运行部署脚本之前，您必须先配置环境文件。

1. **复制环境配置模板**：
```bash
cp docker/.env.docker.example docker/.env
```

2. **编辑配置文件**：
```bash
nano docker/.env  # 或使用您喜欢的编辑器
```

3. **配置必要的API密钥**：
```bash
# API配置（必须配置）
UTU_LLM_API_KEY=your_deepseek_api_key
SERPER_API_KEY=your_serper_api_key
JINA_API_KEY=your_jina_api_key

# Phoenix追踪配置（使用容器主机名，避免IP变化问题）
PHOENIX_ENDPOINT=http://phoenix-phoenix-1:6006/v1/traces
PHOENIX_PROJECT_NAME=youtu_agent
```

### 环境文件检查机制

部署脚本会在构建前自动检查：

- ✅ 检查 `docker/.env` 文件是否存在
- ✅ 验证必要的API密钥是否已配置
- ❌ 如果文件不存在或API密钥未配置，脚本会退出并提供详细的配置指导

**注意**: 脚本不会自动创建或覆盖现有的 `.env` 文件，以保护您的配置安全。

## 常用命令

```bash
# 查看服务日志
docker-compose -f docker/docker-compose.yml logs -f

# 停止服务
docker-compose -f docker/docker-compose.yml down

# 查看容器状态
docker ps

# 重启单个服务
docker-compose -f docker/docker-compose.yml restart youtu-agent
```

## 故障排除

### Phoenix容器未启动
```bash
# 手动启动Phoenix
./deploy.sh --phoenix
```

### 端口被占用
```bash
# 检查端口占用
sudo netstat -tulpn | grep :8848
sudo netstat -tulpn | grep :6006

# 停止占用端口的进程
sudo kill -9 <PID>
```

### 网络连接问题
```bash
# 检查Docker网络
docker network ls
docker network inspect phoenix_default

# 重建网络
docker network rm phoenix_default
./deploy.sh --phoenix
```

### 重建所有服务
```bash
# 完全清理重建
./deploy.sh --clean --phoenix --mode github
```

### 仅删除容器和镜像
```bash
# 删除所有相关容器和镜像，不重新构建
./deploy.sh --remove

# 等同于
./deploy.sh -r
```

## Docker支持的构建参数

Dockerfile现在支持以下构建参数：

```bash
# 直接使用Docker构建（本地模式）
docker build --build-arg BUILD_MODE=local -t youtu-agent .

# 直接使用Docker构建（GitHub模式）
docker build --build-arg BUILD_MODE=github -t youtu-agent .
```

## 技术特性

✅ **智能Phoenix检测**: 自动检查Phoenix容器状态，按需启动
✅ **双模式构建**: 支持本地代码和GitHub最新代码
✅ **容器主机名**: 使用容器名访问，避免IP变化问题
✅ **健康检查**: 内置服务健康检查机制
✅ **优雅错误处理**: 详细的错误信息和恢复建议
✅ **日志分级**: 彩色日志输出，便于调试

## 注意事项

1. 确保Docker和Docker Compose已正确安装
2. 首次运行需要下载镜像，可能需要较长时间
3. 请确保端口8848和6006未被其他服务占用
4. 在生产环境中建议使用`--detach`模式后台运行
