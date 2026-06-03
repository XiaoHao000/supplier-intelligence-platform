"""
需求：实现基于MCP的旅行天气查询服务器，提供实时天气和目的地信息查询工具

v2.1 升级（2026-06-03）：
    - 新增 query_realtime_weather 工具：接入 Open-Meteo 全球气象 API
      返回实时温度、湿度、风速、天气状况和 3-7 天预报
    - 旧 query_weather 重命名为 query_destination_info：查询 MySQL 中
      的目的地静态旅游信息（景区评级、最佳旅游季节等），作为补充数据
    - Open-Meteo 免注册、零 API Key、日调用不限次数，面试可讲"接入了
      全球实时气象 API，零成本高质量数据源"

面试要点：
    Q: 为什么不存 MySQL？
    A: 天气是实时变化数据，存数据库毫无意义。我们接入了 Open-Meteo
       全球气象 API，免注册零延迟，返回当前温度/湿度/风速/天气预报。
    Q: 为什么选 Open-Meteo 而不是和风天气？
    A: Open-Meteo 由 ECMWF（欧洲中期天气预报中心）提供数据，精度高、
       完全免费、无需 API Key，开发效率最高。如果业务需要国内更高精度，
       可以随时切换到和风天气或高德天气 API，架构上只是一行 URL 替换。

架构说明：
    MCP Server 提供带明确参数的 tool 函数，
    A2A server 使用 LangChain Agent + MCP Tools，让 LLM 自动从用户输入中提取参数。
"""

# ==================== 导入依赖 ====================
import json

import httpx
from fastmcp import FastMCP
from config import Config  # 项目配置（数据库连接信息等）
from create_logger import logger  # 日志模块
from mcp_server.base_mcp_server import BaseMCPService, DateEncoder

conf = Config()  # 全局配置实例

# ==================== WMO 天气代码 → 中文描述 ====================
WMO_WEATHER_CODES = {
    0: "晴天☀️",
    1: "大部晴朗🌤️",
    2: "多云⛅",
    3: "阴天☁️",
    45: "有雾🌫️",
    48: "雾凇🌫️",
    51: "小毛毛雨🌧️",
    53: "中毛毛雨🌧️",
    55: "大毛毛雨🌧️",
    56: "小冻雨🌨️",
    57: "大冻雨🌨️",
    61: "小雨🌧️",
    63: "中雨🌧️",
    65: "大雨🌧️",
    66: "小冻雨🌨️",
    67: "大冻雨🌨️",
    71: "小雪❄️",
    73: "中雪❄️",
    75: "大雪❄️",
    77: "雪粒❄️",
    80: "小阵雨🌦️",
    81: "中阵雨🌦️",
    82: "大阵雨🌦️",
    85: "小阵雪🌨️",
    86: "大阵雪🌨️",
    95: "雷暴⛈️",
    96: "雷暴+小冰雹⛈️",
    99: "雷暴+大冰雹⛈️",
}


def _weather_code_to_text(code: int) -> str:
    """WMO 天气代码转中文描述"""
    return WMO_WEATHER_CODES.get(code, f"未知天气(code={code})")


# ==================== 天气查询服务类 ====================
class WeatherService(BaseMCPService):
    """
    旅行天气查询服务类

    双数据源：
    1. Open-Meteo 全球气象 API —— 实时天气 + 多日预报（主力）
    2. MySQL travel_info 表 —— 目的地静态旅游信息（补充）

    继承 BaseMCPService 复用 MySQL 连接管理和 SQL 执行。
    """

    # Open-Meteo API 端点（免费，无需 API Key）
    GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
    WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

    # 中国热门城市坐标映射（减少 API 调用，快速响应）
    CITY_COORDS = {
        "北京": (39.91, 116.40),
        "上海": (31.23, 121.47),
        "广州": (23.13, 113.26),
        "深圳": (22.54, 114.06),
        "成都": (30.57, 104.07),
        "重庆": (29.56, 106.55),
        "西安": (34.26, 108.94),
        "杭州": (30.29, 120.15),
        "南京": (32.06, 118.80),
        "武汉": (30.59, 114.31),
        "长沙": (28.23, 112.94),
        "昆明": (25.04, 102.68),
        "贵阳": (26.65, 106.63),
        "三亚": (18.25, 109.51),
        "海口": (20.04, 110.34),
        "桂林": (25.27, 110.29),
        "丽江": (26.87, 100.23),
        "拉萨": (29.65, 91.14),
        "乌鲁木齐": (43.83, 87.62),
        "哈尔滨": (45.80, 126.53),
        "大连": (38.91, 121.61),
        "青岛": (36.07, 120.38),
        "厦门": (24.48, 118.09),
        "苏州": (31.30, 120.59),
        "张家界": (29.12, 110.48),
        "张家口": (40.77, 114.88),
        "黄山": (30.13, 118.16),
        "敦煌": (40.14, 94.66),
        "九寨沟": (33.26, 103.92),
        "呼伦贝尔": (49.21, 119.77),
        # 英文/拼音别名
        "beijing": (39.91, 116.40),
        "shanghai": (31.23, 121.47),
        "chengdu": (30.57, 104.07),
        "xian": (34.26, 108.94),
        "sanya": (18.25, 109.51),
    }

    def __init__(self):
        super().__init__()  # BaseMCPService 自动处理 MySQL 连接和自动重连
        self._http_client = None

    @property
    def http_client(self) -> httpx.Client:
        """懒加载 HTTP 客户端（同步，配合 MCP 工具函数）"""
        if self._http_client is None:
            self._http_client = httpx.Client(
                timeout=15.0,
                headers={"User-Agent": "SmartTravel/2.1 (Weather MCP)"},
            )
        return self._http_client

    def _geocode(self, city: str) -> list[dict]:
        """
        城市名 → 坐标（优先本地映射，其次 Open-Meteo Geocoding API）

        参数：
            city: 城市名称（中英文均可）

        返回值：
            list[dict]: [{"name": "北京", "lat": 39.91, "lon": 116.40, "country": "中国"}, ...]
        """
        # 1. 先查本地映射
        if city in self.CITY_COORDS:
            lat, lon = self.CITY_COORDS[city]
            logger.info(f"[Geocode] 本地映射命中: {city} → ({lat}, {lon})")
            return [{"name": city, "lat": lat, "lon": lon, "country": "中国"}]

        # 2. 调用 Open-Meteo Geocoding API
        try:
            resp = self.http_client.get(
                self.GEOCODING_URL,
                params={
                    "name": city,
                    "count": 3,
                    "language": "zh",
                    "format": "json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            if results:
                geocoded = []
                for r in results:
                    geocoded.append({
                        "name": r.get("name", city),
                        "lat": r.get("latitude"),
                        "lon": r.get("longitude"),
                        "country": r.get("country", ""),
                        "admin1": r.get("admin1", ""),  # 省/州
                    })
                logger.info(f"[Geocode] API 返回: {city} → {geocoded[0]['name']} ({geocoded[0]['lat']}, {geocoded[0]['lon']})")
                return geocoded
            else:
                logger.warning(f"[Geocode] 未找到城市: {city}")
                return []
        except Exception as e:
            logger.error(f"[Geocode] API 调用失败: {e}")
            return []

    def _fetch_weather(self, lat: float, lon: float, forecast_days: int = 3) -> dict:
        """
        调用 Open-Meteo 获取实时天气和预报

        参数：
            lat: 纬度
            lon: 经度
            forecast_days: 预报天数（1-16），默认3

        返回值：
            dict: 结构化天气数据
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "weather_code,wind_speed_10m,wind_direction_10m,"
                "surface_pressure"
            ),
            "daily": (
                "temperature_2m_max,temperature_2m_min,"
                "weather_code,precipitation_probability_max,"
                "wind_speed_10m_max"
            ),
            "forecast_days": min(max(forecast_days, 1), 7),  # 限制 1-7
            "timezone": "Asia/Shanghai",
        }

        try:
            resp = self.http_client.get(self.WEATHER_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"[Open-Meteo] 获取成功: ({lat}, {lon})")
            return data
        except Exception as e:
            logger.error(f"[Open-Meteo] API 调用失败: {e}")
            raise

    def query_realtime_weather(self, city: str, forecast_days: int = 3) -> str:
        """
        查询城市实时天气（Open-Meteo API）

        流程：
        1. 城市名 → 坐标（本地映射 / Geocoding API）
        2. 坐标 → Open-Meteo 实时天气 + 多日预报
        3. 结果格式化为中文 JSON

        参数：
            city (str): 城市名称（中英文均可），如 "北京"、"成都"、"sanya"
            forecast_days (int): 预报天数（1-7），默认3天

        返回值：
            str: JSON 字符串
        """
        if not city or not city.strip():
            return json.dumps(
                {"status": "error", "message": "请提供城市名称。"},
                ensure_ascii=False,
            )

        city = city.strip()

        # Step 1: 地理编码
        locations = self._geocode(city)
        if not locations:
            return json.dumps(
                {
                    "status": "no_data",
                    "message": f"未找到城市「{city}」，请确认城市名称是否正确（支持中英文）。",
                },
                ensure_ascii=False,
            )

        # 取第一个匹配结果
        best = locations[0]
        lat, lon = best["lat"], best["lon"]
        resolved_name = best.get("name", city)
        admin = best.get("admin1", "")

        # Step 2: 获取天气
        try:
            weather_data = self._fetch_weather(lat, lon, forecast_days)
        except Exception as e:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"获取天气数据失败：{str(e)}。请稍后重试。",
                },
                ensure_ascii=False,
            )

        # Step 3: 格式化输出
        current = weather_data.get("current", {})
        daily = weather_data.get("daily", {})

        current_weather = {
            "温度": f"{current.get('temperature_2m', 'N/A')}°C",
            "体感温度": f"{current.get('apparent_temperature', 'N/A')}°C",
            "相对湿度": f"{current.get('relative_humidity_2m', 'N/A')}%",
            "天气": _weather_code_to_text(current.get("weather_code", -1)),
            "风速": f"{current.get('wind_speed_10m', 'N/A')} km/h",
            "风向": f"{current.get('wind_direction_10m', 'N/A')}°",
            "气压": f"{current.get('surface_pressure', 'N/A')} hPa",
            "数据时间": current.get("time", "N/A"),
        }

        forecast_list = []
        daily_time = daily.get("time", [])
        for i, day in enumerate(daily_time):
            forecast_list.append({
                "日期": day,
                "最高温度": f"{daily.get('temperature_2m_max', [])[i] if i < len(daily.get('temperature_2m_max', [])) else 'N/A'}°C",
                "最低温度": f"{daily.get('temperature_2m_min', [])[i] if i < len(daily.get('temperature_2m_min', [])) else 'N/A'}°C",
                "天气": _weather_code_to_text(daily.get("weather_code", [])[i] if i < len(daily.get("weather_code", [])) else -1),
                "降水概率": f"{daily.get('precipitation_probability_max', [])[i] if i < len(daily.get('precipitation_probability_max', [])) else 'N/A'}%",
                "最大风速": f"{daily.get('wind_speed_10m_max', [])[i] if i < len(daily.get('wind_speed_10m_max', [])) else 'N/A'} km/h",
            })

        location_str = f"{resolved_name}"
        if admin:
            location_str += f"，{admin}"

        result = {
            "status": "success",
            "source": "Open-Meteo (ECMWF 全球气象)",
            "location": location_str,
            "coordinates": {"lat": lat, "lon": lon},
            "current": current_weather,
            "forecast": forecast_list,
        }

        logger.info(f"[query_realtime_weather] 查询完成: {city} → {resolved_name}")
        return json.dumps(result, cls=DateEncoder, ensure_ascii=False)

    def query_destination_info(self, destination: str, info_type: str = None, date: str = None) -> str:
        """
        查询目的地静态旅游信息（MySQL）

        注意：这是辅助数据源，包含景区评级、最佳旅游季节等静态信息。
        实时天气请使用 query_realtime_weather。

        参数：
            destination (str): 目的地，如 "成都"
            info_type (str, optional): 信息类型，如 "景区评级AAAAA"、"国家级风景名胜区"、"最佳旅游季节"
            date (str, optional): 查询日期，格式 YYYY-MM-DD

        返回值：
            str: JSON 字符串
        """
        sql = (
            "SELECT id, destination, info_type, info_code, source_authority, "
            "issue_date, expiry_date, status, info_scope "
            "FROM travel_info "
            "WHERE destination = %s"
        )
        params = [destination]

        if info_type:
            sql += " AND info_type = %s"
            params.append(info_type)

        if date:
            sql += " AND issue_date <= %s AND expiry_date >= %s"
            params.extend([date, date])

        sql += " ORDER BY expiry_date DESC"

        logger.info(f"[query_destination_info] destination={destination}, info_type={info_type}, date={date}")

        return self._execute_query(sql, params)

    # ==================== 向后兼容别名 ====================
    def query_weather(self, destination: str, weather_type: str = None, date: str = None) -> str:
        """
        [已弃用] 请使用 query_destination_info 或 query_realtime_weather

        保留此方法仅为向后兼容旧测试代码。
        """
        logger.info(f"[兼容] query_weather → query_destination_info: {destination}")
        return self.query_destination_info(destination, weather_type, date)

    def close(self):
        """关闭 HTTP 客户端和数据库连接"""
        if self._http_client:
            try:
                self._http_client.close()
            except Exception:
                pass
            self._http_client = None
        super().close()


# ==================== 创建 MCP 服务器 ====================
def create_weather_mcp_server():
    """
    创建并启动旅行天气查询 MCP 服务器

    注册两个工具：
    1. query_realtime_weather — 实时天气（主力，Open-Meteo API）
    2. query_destination_info — 目的地静态信息（辅助，MySQL）
    """

    weather_mcp = FastMCP(
        name="WeatherTools",
        instructions=(
            "旅行天气查询工具，支持：\n"
            "1. 实时天气查询（query_realtime_weather）：接入 Open-Meteo 全球气象 API，\n"
            "   返回当前温度、体感温度、湿度、风速、天气状况和 3-7 天预报。\n"
            "2. 目的地信息查询（query_destination_info）：查询 MySQL 中的静态旅游信息，\n"
            "   如景区评级、最佳旅游季节、文化遗产等。\n"
            "规则：用户问天气时优先用 query_realtime_weather，问景区/评级时用 query_destination_info。"
        ),
    )

    service = WeatherService()

    # --- 工具 1：实时天气（主力） ---
    @weather_mcp.tool(
        name="query_realtime_weather",
        description=(
            "【主力工具】查询城市实时天气和预报，接入 Open-Meteo 全球气象 API。\n"
            "参数：city(城市名，中英文均可，如'北京'/'beijing'), "
            "forecast_days(预报天数1-7，默认3)。\n"
            "返回：当前温度、体感温度、湿度、风速风向、气压、天气状况 + 多日天气预报。\n"
            "示例：query_realtime_weather(city='北京') 或 query_realtime_weather(city='成都', forecast_days=5)\n"
            "适用场景：用户问'今天天气怎么样'、'成都热不热'、'三亚下周天气'等实时天气问题。"
        ),
    )
    def query_realtime_weather(city: str, forecast_days: int = 3) -> str:
        """MCP 工具：实时天气查询"""
        logger.info(f"[MCP工具] 实时天气查询: city={city}, forecast_days={forecast_days}")
        return service.query_realtime_weather(city, forecast_days)

    # --- 工具 2：目的地静态信息（辅助） ---
    @weather_mcp.tool(
        name="query_destination_info",
        description=(
            "【辅助工具】查询目的地静态旅游信息（MySQL），如景区评级、最佳旅游季节、文化遗产等。\n"
            "参数：destination(目的地), info_type(信息类型，可选值：景区评级AAAAA/国家级风景名胜区/"
            "最佳旅游季节/世界文化遗产/国家历史文化名城，可选), "
            "date(查询日期YYYY-MM-DD，可选)。\n"
            "示例：query_destination_info(destination='成都', info_type='景区评级AAAAA')\n"
            "适用场景：用户问'成都有哪些5A景区'、'西安是什么级别的历史文化名城'等静态信息问题。"
        ),
    )
    def query_destination_info(destination: str, info_type: str = None, date: str = None) -> str:
        """MCP 工具：目的地静态信息查询"""
        logger.info(f"[MCP工具] 目的地信息: destination={destination}, info_type={info_type}")
        return service.query_destination_info(destination, info_type, date)

    # 打印服务器信息
    logger.info("=== 天气查询MCP服务器 (v2.1) ===")
    logger.info(f"名称: {weather_mcp.name}")
    logger.info(f"数据源: Open-Meteo 全球气象 API + MySQL 静态信息")
    logger.info(f"描述: {weather_mcp.instructions}")

    # 启动服务器
    try:
        print("🌤️  Weather MCP Server v2.1 启动中...")
        print("   数据源: Open-Meteo (实时天气) + MySQL (目的地信息)")
        print("   访问: http://127.0.0.1:8002/mcp")
        weather_mcp.run(transport="http", host="0.0.0.0", port=8002)
    except Exception as e:
        print(f"服务器启动失败: {e}")


if __name__ == '__main__':
    create_weather_mcp_server()
