# 从未来导入注解功能，允许在类型注解中使用尚未定义的类型
from __future__ import annotations

# 导入必要的库
import argparse  # 用于命令行参数解析
import math  # 用于数学计算
import os  # 用于操作系统相关功能
import re  # 用于正则表达式操作
from pathlib import Path  # 用于路径操作
from typing import Any  # 用于类型注解
from datetime import datetime  # 用于日期时间操作
from zoneinfo import ZoneInfo  # 用于时区操作

import numexpr  # 用于安全计算数学表达式
import requests  # 用于 HTTP 请求
from dotenv import load_dotenv  # 用于加载环境变量
from mcp.server.fastmcp import FastMCP  # 用于创建 MCP 服务器

from app.core.config import ENV_PATH


# 加载环境变量
load_dotenv(dotenv_path=ENV_PATH, override=True)

# 创建 FastMCP 实例
mcp = FastMCP(
    "local-rag-mcp-server",  # 服务器名称
    instructions=(
        "Local MCP server for the professional LangChain agent demo. "
        "It exposes external tools such as weather, calculator, time, and web search."
    ),  # 服务器说明
    host=os.getenv("MCP_HOST", "127.0.0.1"),  # 主机地址，默认 localhost
    port=int(os.getenv("MCP_PORT", "8765")),  # 端口号，默认 8765
)

# 插件管理
def load_plugins():
    """加载插件"""
    # 获取插件目录路径
    configured_dir = os.getenv("PLUGINS_DIR")
    plugins_dir = Path(configured_dir) if configured_dir else Path(__file__).with_name("plugins")
    # 如果插件目录不存在，直接返回
    if not plugins_dir.exists():
        return
    
    # 遍历插件目录中的所有 Python 文件
    for plugin_file in sorted(plugins_dir.glob("*.py")):
        if plugin_file.name.startswith("_"):
            continue
        try:
            # 动态导入插件模块
            module_name = plugin_file.stem
            import importlib.util
            # 创建模块规范
            spec = importlib.util.spec_from_file_location(module_name, plugin_file)
            if spec and spec.loader:
                # 创建模块
                module = importlib.util.module_from_spec(spec)
                # 执行模块
                spec.loader.exec_module(module)
                # 检查模块是否有 register 函数
                if hasattr(module, "register"):
                    # 调用 register 函数注册插件
                    module.register(mcp)
                    print(f"Loaded plugin: {module_name}")
        except Exception as e:
            # 打印加载插件时的错误
            print(f"Error loading plugin {plugin_file.name}: {e}")

# 获取天气的工具
@mcp.tool()
def get_weather(city: str) -> dict[str, Any]:
    """Get current weather for a city using the Open-Meteo public API."""

    # 调用地理编码 API 获取城市坐标
    geo_response = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1, "language": "zh", "format": "json"},  # 参数
        timeout=15,  # 超时时间
    )
    # 检查响应状态
    geo_response.raise_for_status()
    # 解析响应 JSON
    matches = geo_response.json().get("results") or []
    # 如果没有找到城市
    if not matches:
        return {"error": f"未找到城市：{city}"}

    # 获取第一个匹配结果
    place = matches[0]
    # 调用天气 API 获取天气信息
    weather_response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": place["latitude"],  # 纬度
            "longitude": place["longitude"],  # 经度
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",  # 要获取的天气数据
            "timezone": "auto",  # 自动时区
        },
        timeout=15,  # 超时时间
    )
    # 检查响应状态
    weather_response.raise_for_status()
    # 解析响应 JSON
    current = weather_response.json()["current"]
    # 返回天气信息
    return {
        "location": f"{place.get('name')}, {place.get('country')}",  # 位置
        "temperature_c": current.get("temperature_2m"),  # 温度（摄氏度）
        "apparent_temperature_c": current.get("apparent_temperature"),  # 体感温度（摄氏度）
        "humidity_percent": current.get("relative_humidity_2m"),  # 湿度（百分比）
        "wind_speed_kmh": current.get("wind_speed_10m"),  # 风速（km/h）
        "weather_code": current.get("weather_code"),  # 天气代码
        "time": current.get("time"),  # 时间
    }


# 计算数学表达式的工具
@mcp.tool()
def calculate(expression: str) -> dict[str, Any]:
    """Calculate a numeric expression."""

    return evaluate_expression(expression)


def evaluate_expression(expression: str) -> dict[str, Any]:
    expression = expression.strip()
    
    # 检查表达式长度，防止过长表达式
    if len(expression) > 100:
        return {"error": "Expression too long. Maximum length is 100 characters."}
    
    # 更严格的正则表达式，只允许安全的数学运算符和数字
    if not re.fullmatch(r"[0-9+\-*/()., eE]+", expression):
        return {"error": "Only numeric expressions are allowed."}
    
    # 检查是否包含潜在的危险模式
    dangerous_patterns = ["import", "exec", "eval", "open", "file", "__", "sys", "os"]
    for pattern in dangerous_patterns:
        if pattern in expression.lower():
            return {"error": "Expression contains potentially dangerous content."}
    
    try:
        # 使用 numexpr 进行安全计算
        value = numexpr.evaluate(expression, local_dict={}, global_dict={}).item()
        # 检查结果是否为有效数字
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            return {"error": "Calculation resulted in an invalid number."}
    except Exception as exc:
        # 捕获计算错误
        return {"error": f"Calculation failed: {exc}"}
    return {"expression": expression, "result": value}


# 获取当前时间的工具
@mcp.tool()
def get_current_time(timezone: str = "Asia/Shanghai") -> dict[str, Any]:
    """Get current time for an IANA timezone."""

    try:
        # 获取指定时区的当前时间
        now = datetime.now(ZoneInfo(timezone))
    except Exception as exc:
        # 捕获时区错误
        return {"error": f"Invalid timezone: {timezone}. Error: {exc}"}
    # 返回当前时间
    return {"timezone": timezone, "time": now.isoformat(timespec="seconds")}


# 网络搜索工具
@mcp.tool()
def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Search the web and return titles, snippets, and URLs."""

    try:
        # 尝试导入 DDGS
        from ddgs import DDGS

        # 执行搜索
        results = DDGS().text(query, max_results=max_results)
        # 构建结果列表
        items = [
            {
                "title": item.get("title"),  # 标题
                "snippet": item.get("body"),  # 摘要
                "url": item.get("href"),  # URL
            }
            for item in results
        ]
        # 返回搜索结果
        return {"query": query, "results": items}
    except ImportError:
        # 捕获导入错误
        return {"error": "Web search is not available. Please install duckduckgo-search package."}
    except Exception as exc:
        # 捕获其他错误
        return {"error": f"Web search failed: {exc}"}


# 健康检查工具
@mcp.tool()
def health_check() -> dict[str, Any]:
    """Check the health status of the MCP server and its dependencies."""
    
    # 初始化依赖状态
    dependencies = {
        "duckduckgo-search": False,
        "numexpr": False,
        "requests": False,
    }
    
    # 检查 duckduckgo-search 依赖
    try:
        from ddgs import DDGS
        dependencies["duckduckgo-search"] = True
    except ImportError:
        pass
    
    # 检查 numexpr 依赖
    try:
        import numexpr
        dependencies["numexpr"] = True
    except ImportError:
        pass
    
    # 检查 requests 依赖
    try:
        import requests
        dependencies["requests"] = True
    except ImportError:
        pass
    
    # 返回健康检查结果
    return {
        "status": "healthy",  # 服务状态
        "dependencies": dependencies,  # 依赖状态
        "available_tools": [  # 可用工具列表
            "get_weather",
            "calculate",
            "get_current_time",
            "web_search" if dependencies["duckduckgo-search"] else "web_search (unavailable)",
            "health_check"
        ]
    }


# 主函数
def main() -> None:
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description="Run the local RAG MCP server.")
    # 添加 transport 参数
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],  # 可选值
        default=os.getenv("MCP_TRANSPORT", "stdio"),  # 默认值
        help="MCP transport to use. Use streamable-http for a long-running server.",  # 帮助信息
    )
    # 解析命令行参数
    args = parser.parse_args()
    
    # 加载插件
    load_plugins()
    
    # 运行 MCP 服务器
    mcp.run(transport=args.transport)


# 如果作为主模块运行
if __name__ == "__main__":
    # 调用主函数
    main()
