from __future__ import annotations

from typing import Any

import requests


WEATHER_CODE_TEXT = {
    0: "晴",
    1: "大致晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "中等毛毛雨",
    55: "较强毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "小阵雨",
    81: "中等阵雨",
    82: "强阵雨",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴大冰雹",
}

CITY_ALIASES = {
    "北京": "Beijing",
    "上海": "Shanghai",
    "广州": "Guangzhou",
    "深圳": "Shenzhen",
    "杭州": "Hangzhou",
    "南京": "Nanjing",
    "成都": "Chengdu",
    "重庆": "Chongqing",
    "武汉": "Wuhan",
    "西安": "Xi'an",
    "昆明": "Kunming",
    "大理": "Dali",
    "下关": "Dali",
    "丽江": "Lijiang",
    "玉溪": "Yuxi",
    "曲靖": "Qujing",
    "保山": "Baoshan",
    "普洱": "Pu'er",
    "临沧": "Lincang",
    "昭通": "Zhaotong",
}

RAIN_CODES = {51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99}
SNOW_CODES = {71, 73, 75}


def register(mcp):
    @mcp.tool()
    def weather_forecast(city: str) -> dict[str, Any]:
        """Get current weather and a short forecast for a city."""

        place = _geocode_city(city)
        if "error" in place:
            return place

        weather_response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": (
                    "temperature_2m,relative_humidity_2m,apparent_temperature,"
                    "weather_code,wind_speed_10m,precipitation"
                ),
                "daily": (
                    "weather_code,temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max,uv_index_max"
                ),
                "forecast_days": 3,
                "timezone": "auto",
            },
            timeout=15,
        )
        weather_response.raise_for_status()
        data = weather_response.json()
        current = data.get("current", {})
        daily = data.get("daily", {})
        code = current.get("weather_code")

        return {
            "location": place["location"],
            "current": {
                "time": current.get("time"),
                "temperature_c": current.get("temperature_2m"),
                "apparent_temperature_c": current.get("apparent_temperature"),
                "humidity_percent": current.get("relative_humidity_2m"),
                "wind_speed_kmh": current.get("wind_speed_10m"),
                "precipitation_mm": current.get("precipitation"),
                "weather_code": code,
                "weather": WEATHER_CODE_TEXT.get(code, f"未知天气代码 {code}"),
            },
            "daily": _daily_forecast(daily),
        }

    @mcp.tool()
    def weather_news(city: str, max_results: int = 5) -> dict[str, Any]:
        """Search weather-related news and alerts for a city."""

        try:
            from ddgs import DDGS
        except ImportError:
            return {"error": "Weather news search requires the ddgs package."}

        query = f"{city} 天气 预警 新闻 暴雨 高温 台风"
        try:
            results = DDGS().text(query, max_results=max_results)
        except Exception as exc:
            return {"error": f"Weather news search failed: {exc}"}

        return {
            "query": query,
            "results": [
                {
                    "title": item.get("title"),
                    "snippet": item.get("body"),
                    "url": item.get("href"),
                }
                for item in results
            ],
        }

    @mcp.tool()
    def weather_advisor(city: str) -> dict[str, Any]:
        """Get weather, related news, and practical advice for a city."""

        forecast = weather_forecast(city)
        news = weather_news(city, max_results=5)
        if "error" in forecast:
            return {"city": city, "forecast": forecast, "news": news, "advice": []}

        current = forecast.get("current", {})
        daily = forecast.get("daily", [])
        advice = _build_advice(current, daily)

        return {
            "city": city,
            "forecast": forecast,
            "news": news,
            "advice": advice,
            "note": "天气数据来自 Open-Meteo，新闻来自网页搜索结果；出行前请结合当地官方预警确认。",
        }


def _geocode_city(city: str) -> dict[str, Any]:
    candidates = _city_candidates(city)
    matches = []
    for candidate in candidates:
        response = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": candidate, "count": 1, "language": "zh", "format": "json"},
            timeout=15,
        )
        response.raise_for_status()
        matches = response.json().get("results") or []
        if matches:
            break
    if not matches:
        return {"error": f"未找到城市：{city}"}

    place = matches[0]
    return {
        "name": place.get("name"),
        "country": place.get("country"),
        "admin1": place.get("admin1"),
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "location": ", ".join(
            item for item in [place.get("name"), place.get("admin1"), place.get("country")] if item
        ),
    }


def _city_candidates(city: str) -> list[str]:
    clean = city.strip()
    stripped = clean.removesuffix("市").removesuffix("区").removesuffix("县")
    alias = CITY_ALIASES.get(stripped) or CITY_ALIASES.get(clean)
    candidates = []
    if alias:
        candidates.append(alias)
    candidates.append(clean)
    if stripped and stripped != clean:
        candidates.append(stripped)
    return list(dict.fromkeys(candidates))


def _daily_forecast(daily: dict[str, list[Any]]) -> list[dict[str, Any]]:
    days = []
    for idx, day in enumerate(daily.get("time", [])):
        code = _at(daily, "weather_code", idx)
        days.append(
            {
                "date": day,
                "weather_code": code,
                "weather": WEATHER_CODE_TEXT.get(code, f"未知天气代码 {code}"),
                "temperature_max_c": _at(daily, "temperature_2m_max", idx),
                "temperature_min_c": _at(daily, "temperature_2m_min", idx),
                "precipitation_probability_percent": _at(
                    daily,
                    "precipitation_probability_max",
                    idx,
                ),
                "uv_index_max": _at(daily, "uv_index_max", idx),
            }
        )
    return days


def _at(data: dict[str, list[Any]], key: str, idx: int) -> Any:
    values = data.get(key) or []
    return values[idx] if idx < len(values) else None


def _build_advice(current: dict[str, Any], daily: list[dict[str, Any]]) -> list[str]:
    advice = []
    temperature = current.get("temperature_c")
    apparent = current.get("apparent_temperature_c")
    wind = current.get("wind_speed_kmh")
    code = current.get("weather_code")
    today = daily[0] if daily else {}
    rain_probability = today.get("precipitation_probability_percent")
    uv_index = today.get("uv_index_max")

    if temperature is not None:
        if temperature >= 32 or (apparent is not None and apparent >= 35):
            advice.append("高温明显，建议减少正午户外活动，补水并注意防暑。")
        elif temperature <= 5:
            advice.append("气温较低，建议穿厚外套，老人和儿童注意保暖。")
        elif temperature <= 15:
            advice.append("体感偏凉，建议加一件外套。")
        else:
            advice.append("温度整体适中，日常通勤按常规穿着即可。")

    if code in RAIN_CODES or (rain_probability is not None and rain_probability >= 50):
        advice.append("有降水风险，建议带伞，骑行或驾车注意路面湿滑。")
    if code in SNOW_CODES:
        advice.append("有降雪风险，注意防滑和道路结冰。")
    if wind is not None and wind >= 30:
        advice.append("风力较大，避免在广告牌、临时搭建物和树下长时间停留。")
    if uv_index is not None and uv_index >= 6:
        advice.append("紫外线较强，建议使用防晒霜、帽子或墨镜。")

    if not advice:
        advice.append("暂无明显天气风险，出行前可再查看当地官方预警。")
    return advice
