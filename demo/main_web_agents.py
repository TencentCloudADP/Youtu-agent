#!/usr/bin/env python3
"""
支持智能体切换的WebUI启动脚本
使用WebUIAgents而不是WebUIChatbot，支持智能体列表和切换功能
"""

import argparse
from utu.ui.webui_agents import WebUIAgents
from utu.utils.env import EnvUtils

DEFAULT_CONFIG = "examples/svg_generator.yaml"  # 默认智能体配置
DEFAULT_IP = EnvUtils.get_env("UTU_WEBUI_IP", "0.0.0.0")
DEFAULT_PORT = EnvUtils.get_env("UTU_WEBUI_PORT", "8848")
DEFAULT_AUTOLOAD = EnvUtils.get_env("UTU_WEBUI_AUTOLOAD", "false") == "true"

def main():
    """启动支持智能体切换的WebUI"""

    parser = argparse.ArgumentParser(
        description="启动支持智能体切换的Youtu-Agent WebUI"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=DEFAULT_CONFIG,
        help="默认智能体配置文件 (例如: examples/svg_generator.yaml)"
    )
    parser.add_argument(
        "--ip",
        type=str,
        default=DEFAULT_IP,
        help="监听IP地址"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="监听端口"
    )
    parser.add_argument(
        "--autoload",
        action="store_true",
        default=DEFAULT_AUTOLOAD,
        help="启用自动重载"
    )

    args = parser.parse_args()

    print("🚀 启动Youtu-Agent WebUI...")
    print(f"📱 界面类型: WebUIAgents (支持智能体切换)")
    print(f"🤖 默认智能体: {args.config}")
    print(f"🌐 访问地址: http://{args.ip}:{args.port}")
    print(f"🔄 自动重载: {'启用' if args.autoload else '禁用'}")
    print()

    # 创建WebUIAgents实例
    webui = WebUIAgents(default_config=args.config)

    print("✅ WebUI已启动！")
    print("💡 功能说明:")
    print("  - 支持智能体列表查看")
    print("  - 支持智能体切换")
    print("  - 支持元智能体生成")
    print("  - 自动发现generated目录下的智能体")
    print()

    # 启动WebUI
    webui.launch(ip=args.ip, port=args.port, autoload=args.autoload)

if __name__ == "__main__":
    main()
