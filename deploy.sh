#!/bin/bash

# =============================================================================
# Youtu-Agent 一键部署脚本
# 功能：自动检查并启动Phoenix容器，然后启动Youtu-Agent
# 作者：Songm
# =============================================================================

set -e  # 遇到错误时退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

# 显示帮助信息
show_help() {
    cat << EOF
Youtu-Agent 一键部署脚本

用法: $0 [选项]

选项:
    -m, --mode <local|github>    构建模式 (默认: local)
                                local:  使用本地代码构建
                                github: 从GitHub拉取最新代码构建
    -p, --phoenix               强制重启Phoenix容器
    -c, --clean                 清理旧容器和镜像
    -r, --remove                删除旧容器和镜像，不重新构建
    -d, --detach                后台运行模式
    -h, --help                  显示此帮助信息

示例:
    $0                          # 使用本地代码，自动模式
    $0 -m github                # 从GitHub构建
    $0 -p -c                    # 强制重启Phoenix并清理旧容器
    $0 -m local -d              # 本地构建，后台运行
    $0 -r                       # 仅删除容器和镜像，不重新构建

EOF
}

# 检查必要工具
check_requirements() {
    log_info "检查必要工具..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose 未安装，请先安装 Docker Compose"
        exit 1
    fi

    log_info "工具检查完成 ✓"
}

# 检查Phoenix容器状态
check_phoenix() {
    log_info "检查Phoenix容器状态..."

    # 检查Phoenix容器是否存在并运行
    if docker ps --format "table {{.Names}}" | grep -q "phoenix-phoenix-1"; then
        log_info "Phoenix容器正在运行 ✓"
        return 0
    elif docker ps -a --format "table {{.Names}}" | grep -q "phoenix-phoenix-1"; then
        log_warn "Phoenix容器存在但未运行，正在启动..."
        docker start phoenix-phoenix-1 || {
            log_error "启动Phoenix容器失败"
            return 1
        }
        log_info "Phoenix容器已启动 ✓"
        return 0
    else
        log_warn "未发现Phoenix容器"
        return 1
    fi
}

# 自动安装Phoenix
install_phoenix() {
    log_info "正在安装Phoenix容器..."

    # 创建临时目录
    TEMP_DIR=$(mktemp -d)
    cd "$TEMP_DIR"

    # 下载Phoenix docker-compose配置
    cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  phoenix:
    image: arizephoenix/phoenix:latest
    ports:
      - "6006:6006"
      - "4317:4317"
    environment:
      - PHOENIX_SQL_DATABASE_URL=postgresql://phoenix:phoenix@db:5432/phoenix
    depends_on:
      - db
    networks:
      - phoenix_default

  db:
    image: postgres:16
    environment:
      - POSTGRES_USER=phoenix
      - POSTGRES_PASSWORD=phoenix
      - POSTGRES_DB=phoenix
    volumes:
      - phoenix_db_data:/var/lib/postgresql/data
    networks:
      - phoenix_default

volumes:
  phoenix_db_data:

networks:
  phoenix_default:
    name: phoenix_default
EOF

    # 启动Phoenix
    log_info "启动Phoenix服务..."
    docker-compose up -d

    # 等待Phoenix启动
    log_info "等待Phoenix服务启动..."
    for i in {1..30}; do
        if curl -f http://localhost:6006 &>/dev/null; then
            log_info "Phoenix服务启动成功 ✓"
            cd - > /dev/null
            rm -rf "$TEMP_DIR"
            return 0
        fi
        sleep 2
        echo -n "."
    done

    log_error "Phoenix服务启动超时"
    cd - > /dev/null
    rm -rf "$TEMP_DIR"
    return 1
}

# 检查并加载环境变量
check_and_load_env() {
    log_info "检查环境配置文件..."

    # 检查.env文件是否存在
    if [[ ! -f docker/.env ]]; then
        log_error ".env文件不存在！"
        echo
        log_info "请按以下步骤配置环境文件："
        echo "  1. 复制示例配置文件："
        echo "     cp docker/.env.docker.example docker/.env"
        echo "  2. 编辑配置文件，设置您的API密钥："
        echo "     nano docker/.env  # 或使用其他编辑器"
        echo "  3. 配置以下必要的API密钥："
        echo "     - UTU_LLM_API_KEY     (DeepSeek API密钥)"
        echo "     - SERPER_API_KEY      (Serper搜索API密钥)"
        echo "     - JINA_API_KEY        (Jina Reader API密钥)"
        echo
        log_info "配置完成后，重新运行部署脚本。"
        exit 1
    fi

    # 进入docker目录加载环境变量
    cd docker/

    # 加载环境变量
    log_info "加载环境配置 ✓"
    set -a  # 自动导出所有变量
    source .env
    set +a  # 关闭自动导出

    # 验证必要的环境变量
    local missing_vars=()

    if [[ -z "$UTU_LLM_API_KEY" || "$UTU_LLM_API_KEY" == "your_api_key_here" || "$UTU_LLM_API_KEY" == "" ]]; then
        missing_vars+=("UTU_LLM_API_KEY")
    fi

    if [[ -z "$SERPER_API_KEY" || "$SERPER_API_KEY" == "your_serper_api_key_here" || "$SERPER_API_KEY" == "" ]]; then
        missing_vars+=("SERPER_API_KEY")
    fi

    if [[ -z "$JINA_API_KEY" || "$JINA_API_KEY" == "your_jina_api_key_here" || "$JINA_API_KEY" == "" ]]; then
        missing_vars+=("JINA_API_KEY")
    fi

    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        log_warn "检测到未配置的API密钥："
        for var in "${missing_vars[@]}"; do
            echo "  - $var"
        done
        echo
        log_warn "请编辑 docker/.env 文件，配置上述API密钥后重新运行。"
        echo "提示：您可以使用以下命令编辑配置文件："
        echo "  nano docker/.env"
        cd ..
        exit 1
    fi

    log_info "环境变量验证通过 ✓"
    cd ..
}
clean_old() {
    log_info "清理旧的Youtu-Agent容器和镜像..."

    # 停止并删除容器
    if docker ps -a --format "table {{.Names}}" | grep -q "docker-youtu-agent-1"; then
        log_debug "停止并删除旧的Youtu-Agent容器..."
        docker stop docker-youtu-agent-1 2>/dev/null || true
        docker rm docker-youtu-agent-1 2>/dev/null || true
    fi

    # 删除旧镜像
    if docker images --format "table {{.Repository}}" | grep -q "docker-youtu-agent"; then
        log_debug "删除旧的Youtu-Agent镜像..."
        docker rmi docker-youtu-agent 2>/dev/null || true
    fi

    log_info "清理完成 ✓"
}

# 仅删除容器和镜像，不重新构建
remove_only() {
    log_info "删除Youtu-Agent容器和镜像..."

    # 进入docker目录
    cd docker/

    # 停止并删除服务
    log_debug "使用docker-compose停止服务..."
    docker-compose down 2>/dev/null || true

    # 删除镜像
    if docker images --format "table {{.Repository}}" | grep -q "docker-youtu-agent"; then
        log_debug "删除Youtu-Agent镜像..."
        docker rmi docker-youtu-agent 2>/dev/null || true
    fi

    # 清理未使用的镜像和容器
    log_debug "清理未使用的Docker资源..."
    docker system prune -f 2>/dev/null || true

    cd ..

    log_info "删除完成 ✓"
    log_info "=================================="
    log_info "容器和镜像已成功删除！"
    log_info "=================================="
}

# 构建和启动Youtu-Agent
build_and_start() {
    local build_mode=$1
    local detach_mode=$2

    log_info "构建Youtu-Agent (模式: $build_mode)..."

    # 进入docker目录
    cd docker/

    # 使用已验证的环境配置
    log_info "使用现有环境配置 .env ✓"

    # 更新docker-compose.yml以支持构建参数
    cat > docker-compose.yml << EOF
version: '3.8'

services:
  youtu-agent:
    build:
      context: ..
      dockerfile: docker/Dockerfile
      args:
        BUILD_MODE: $build_mode
    ports:
      - "8848:8848"
    volumes:
      - "./.env:/youtu-agent/.env"
    environment:
      # 从.env文件加载环境变量
      - UTU_LLM_TYPE=\${UTU_LLM_TYPE}
      - UTU_LLM_MODEL=\${UTU_LLM_MODEL}
      - UTU_LLM_BASE_URL=\${UTU_LLM_BASE_URL}
      - UTU_LLM_API_KEY=\${UTU_LLM_API_KEY}
      - SERPER_API_KEY=\${SERPER_API_KEY}
      - JINA_API_KEY=\${JINA_API_KEY}
      # Phoenix相关配置从.env文件加载，以支持主机名方式访问
      - PHOENIX_PROJECT_NAME=\${PHOENIX_PROJECT_NAME}
      - DB_URL=\${DB_URL}
      - UTU_LOG_LEVEL=\${UTU_LOG_LEVEL}
      - UTU_WEBUI_PORT=\${UTU_WEBUI_PORT}
      - UTU_WEBUI_IP=\${UTU_WEBUI_IP}
    env_file:
      - .env
    networks:
      - phoenix_default
    restart: unless-stopped

networks:
  phoenix_default:
    external: true
EOF

    # 构建和启动
    local compose_cmd="docker-compose up --build"
    if [[ "$detach_mode" == "true" ]]; then
        compose_cmd="$compose_cmd -d"
    fi

    log_info "执行: $compose_cmd"
    eval $compose_cmd

    cd ..
}

# 检查服务状态
check_services() {
    log_info "检查服务状态..."

    # 检查Phoenix
    if curl -f http://localhost:6006 &>/dev/null; then
        log_info "Phoenix服务正常 ✓ (http://localhost:6006)"
    else
        log_warn "Phoenix服务可能未正常启动"
    fi

    # 检查Youtu-Agent
    sleep 10  # 等待服务启动
    if curl -f http://localhost:8848 &>/dev/null; then
        log_info "Youtu-Agent服务正常 ✓ (http://localhost:8848)"
    else
        log_warn "Youtu-Agent服务可能未正常启动"
    fi
}

# 主函数
main() {
    local build_mode="local"
    local force_phoenix=false
    local clean_old_flag=false
    local remove_only_flag=false
    local detach_mode=false

    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -m|--mode)
                build_mode="$2"
                if [[ "$build_mode" != "local" && "$build_mode" != "github" ]]; then
                    log_error "无效的构建模式: $build_mode"
                    show_help
                    exit 1
                fi
                shift 2
                ;;
            -p|--phoenix)
                force_phoenix=true
                shift
                ;;
            -c|--clean)
                clean_old_flag=true
                shift
                ;;
            -r|--remove)
                remove_only_flag=true
                shift
                ;;
            -d|--detach)
                detach_mode=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # 如果只是删除，执行删除操作后退出
    if [[ "$remove_only_flag" == "true" ]]; then
        check_requirements
        remove_only
        exit 0
    fi

    log_info "开始部署Youtu-Agent..."
    log_info "构建模式: $build_mode"
    log_info "运行模式: $([ "$detach_mode" == "true" ] && echo "后台" || echo "前台")"

    # 检查工具
    check_requirements

    # 检查并加载环境变量
    check_and_load_env

    # 清理旧容器（如果需要）
    if [[ "$clean_old_flag" == "true" ]]; then
        clean_old
    fi

    # 检查或安装Phoenix
    if [[ "$force_phoenix" == "true" ]] || ! check_phoenix; then
        if [[ "$force_phoenix" == "true" ]]; then
            log_info "强制重新安装Phoenix..."
        fi
        install_phoenix || {
            log_error "Phoenix安装失败"
            exit 1
        }
    fi

    # 构建和启动Youtu-Agent
    build_and_start "$build_mode" "$detach_mode"

    # 检查服务状态
    if [[ "$detach_mode" == "true" ]]; then
        check_services

        log_info "==================================="
        log_info "部署完成！"
        log_info "Phoenix追踪: http://localhost:6006"
        log_info "Youtu-Agent: http://localhost:8848"
        log_info "==================================="
        log_info "查看日志: docker-compose -f docker/docker-compose.yml logs -f"
        log_info "停止服务: docker-compose -f docker/docker-compose.yml down"
    fi
}

# 捕获退出信号
trap 'log_warn "部署被中断"; exit 1' INT TERM

# 执行主函数
main "$@"
