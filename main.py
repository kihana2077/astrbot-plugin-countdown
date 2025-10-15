import os
import json
import aiofiles
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig


@register("countdown", "开发者", "倒数日管理插件", "1.0.0", "https://github.com/your-repo")
class CountdownPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        
        # 确保数据目录存在 - 正确的路径结构
        # data/plugin_data/astrbot_plugin_countdown/countdown_data.json
        self.data_dir = os.path.join("data", "plugin_data", "astrbot_plugin_countdown")
        os.makedirs(self.data_dir, exist_ok=True)
        self.data_file = os.path.join(self.data_dir, "countdown_data.json")
        
        # 创建初始数据文件（如果不存在）
        asyncio.create_task(self._initialize_data_file())
        
    async def _initialize_data_file(self):
        """初始化数据文件"""
        try:
            if not os.path.exists(self.data_file):
                await self._save_data({})
                logger.info("倒数日插件数据文件已创建")
        except Exception as e:
            logger.error(f"初始化数据文件失败: {e}")

    async def _load_data(self) -> Dict[str, Any]:
        """加载倒数日数据"""
        try:
            # 确保文件存在
            if not os.path.exists(self.data_file):
                await self._save_data({})
                
            async with aiofiles.open(self.data_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content) if content else {}
        except Exception as e:
            logger.error(f"加载数据失败: {e}")
            return {}

    async def _save_data(self, data: Dict[str, Any]) -> bool:
        """保存倒数日数据"""
        try:
            async with aiofiles.open(self.data_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            return True
        except Exception as e:
            logger.error(f"保存数据失败: {e}")
            return False

    def _get_storage_key(self, event: AstrMessageEvent) -> str:
        """获取存储键名：群聊用群ID，私聊用用户ID"""
        if event.get_group_id():
            return f"group_{event.get_group_id()}"
        else:
            return f"private_{event.get_sender_id()}"

    def _format_date(self, date_str: str, target_date: datetime) -> str:
        """根据配置格式化日期"""
        date_format = self.config.get("date_format", "YYYY年MM月DD日")
        if date_format == "YYYY-MM-DD":
            return target_date.strftime("%Y-%m-%d")
        elif date_format == "MM/DD/YYYY":
            return target_date.strftime("%m/%d/%Y")
        else:  # 默认格式
            return target_date.strftime("%Y年%m月%d日")

    async def _get_countdowns(self, event: AstrMessageEvent) -> List[Dict[str, Any]]:
        """获取用户的倒数日列表"""
        data = await self._load_data()
        storage_key = self._get_storage_key(event)
        return data.get(storage_key, [])

    async def _save_countdowns(self, event: AstrMessageEvent, countdowns: List[Dict[str, Any]]) -> bool:
        """保存用户的倒数日列表"""
        data = await self._load_data()
        storage_key = self._get_storage_key(event)
        data[storage_key] = countdowns
        return await self._save_data(data)

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """解析日期字符串，支持多种格式"""
        formats = ["%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%m月%d日"]  # 最后一种格式自动补全年份
        
        for fmt in formats:
            try:
                if fmt == "%m月%d日":  # 自动补全当前年份
                    current_year = datetime.now().year
                    date_str_with_year = f"{current_year}年{date_str}"
                    return datetime.strptime(date_str_with_year, "%Y年%m月%d日")
                else:
                    return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    def _calculate_days_left(self, target_date: datetime) -> int:
        """计算剩余天数"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        delta = target_date - today
        return delta.days

    @filter.command("add_countdown")
    async def add_countdown(self, event: AstrMessageEvent, name: str, target_date_str: str):
        """添加倒数日
        用法: /add_countdown 事件名称 目标日期(YYYY-MM-DD或MM月DD日)
        示例: /add_countdown 生日 12-25 或 /add_countdown 春节 2025-01-29
        """
        # 检查权限
        if event.get_group_id() and not self.config.get("allow_group", True):
            yield event.plain_result("群聊中已禁用倒数日功能")
            return
        
        if not event.get_group_id() and not self.config.get("allow_private", True):
            yield event.plain_result("私聊中已禁用倒数日功能")
            return

        # 解析日期
        target_date = self._parse_date(target_date_str)
        if not target_date:
            yield event.plain_result("日期格式错误，请使用 YYYY-MM-DD 或 MM月DD日 格式")
            return

        # 检查日期是否在过去
        if self._calculate_days_left(target_date) < 0:
            yield event.plain_result("目标日期不能是过去的时间")
            return

        # 获取当前倒数日列表
        countdowns = await self._get_countdowns(event)
        max_count = self.config.get("max_countdowns", 10)
        
        if len(countdowns) >= max_count:
            yield event.plain_result(f"已达到最大倒数日数量限制({max_count}个)")
            return

        # 检查是否已存在同名事件
        for cd in countdowns:
            if cd["name"] == name:
                yield event.plain_result(f"已存在名为「{name}」的倒数日")
                return

        # 添加新倒数日
        new_countdown = {
            "name": name,
            "target_date": target_date.strftime("%Y-%m-%d"),
            "created_date": datetime.now().strftime("%Y-%m-%d"),
            "remind_days": self.config.get("default_remind_days", 1)
        }
        countdowns.append(new_countdown)

        if await self._save_countdowns(event, countdowns):
            days_left = self._calculate_days_left(target_date)
            formatted_date = self._format_date(target_date_str, target_date)
            yield event.plain_result(
                f"✅ 已添加倒数日「{name}」\n"
                f"📅 目标日期: {formatted_date}\n"
                f"⏳ 剩余天数: {days_left}天"
            )
        else:
            yield event.plain_result("添加失败，请稍后重试")

    @filter.command("del_countdown")
    async def del_countdown(self, event: AstrMessageEvent, name_or_index: str):
        """删除倒数日
        用法: /del_countdown 事件名称或序号
        示例: /del_countdown 生日 或 /del_countdown 1
        """
        countdowns = await self._get_countdowns(event)
        
        if not countdowns:
            yield event.plain_result("暂无倒数日记录")
            return

        # 尝试按序号删除
        if name_or_index.isdigit():
            index = int(name_or_index) - 1
            if 0 <= index < len(countdowns):
                removed = countdowns.pop(index)
                if await self._save_countdowns(event, countdowns):
                    yield event.plain_result(f"✅ 已删除倒数日「{removed['name']}」")
                else:
                    yield event.plain_result("删除失败，请稍后重试")
                return

        # 按名称删除
        for i, cd in enumerate(countdowns):
            if cd["name"] == name_or_index:
                removed = countdowns.pop(i)
                if await self._save_countdowns(event, countdowns):
                    yield event.plain_result(f"✅ 已删除倒数日「{removed['name']}」")
                else:
                    yield event.plain_result("删除失败，请稍后重试")
                return

        yield event.plain_result("未找到对应的倒数日")

    @filter.command("list_countdown")
    async def list_countdown(self, event: AstrMessageEvent):
        """列出所有倒数日"""
        countdowns = await self._get_countdowns(event)
        
        if not countdowns:
            yield event.plain_result("暂无倒数日记录")
            return

        result = "📋 倒数日列表:\n"
        for i, cd in enumerate(countdowns, 1):
            target_date = datetime.strptime(cd["target_date"], "%Y-%m-%d")
            days_left = self._calculate_days_left(target_date)
            formatted_date = self._format_date(cd["target_date"], target_date)
            
            result += f"{i}. {cd['name']} - {formatted_date} (剩余{days_left}天)\n"

        yield event.plain_result(result.strip())

    @filter.command("countdown")
    async def check_countdown(self, event: AstrMessageEvent, name: str = ""):
        """查看特定倒数日或所有倒数日
        用法: /countdown [事件名称]
        示例: /countdown 或 /countdown 生日
        """
        countdowns = await self._get_countdowns(event)
        
        if not countdowns:
            yield event.plain_result("暂无倒数日记录")
            return

        if name:  # 查看特定倒数日
            for cd in countdowns:
                if cd["name"] == name:
                    target_date = datetime.strptime(cd["target_date"], "%Y-%m-%d")
                    days_left = self._calculate_days_left(target_date)
                    formatted_date = self._format_date(cd["target_date"], target_date)
                    
                    # 计算进度条
                    total_days = (target_date - datetime.strptime(cd["created_date"], "%Y-%m-%d")).days
                    passed_days = total_days - days_left
                    progress = min(int(passed_days / total_days * 20), 20) if total_days > 0 else 20
                    progress_bar = "█" * progress + "░" * (20 - progress)
                    
                    result = (
                        f"🎯 事件: {cd['name']}\n"
                        f"📅 目标日期: {formatted_date}\n"
                        f"⏳ 剩余天数: {days_left}天\n"
                        f"📊 进度: [{progress_bar}] {passed_days}/{total_days}天"
                    )
                    
                    if days_left <= cd["remind_days"]:
                        result += f"\n🔔 即将到来! ({days_left}天后)"
                    
                    yield event.plain_result(result)
                    return
            
            yield event.plain_result(f"未找到名为「{name}」的倒数日")
        
        else:  # 查看所有倒数日
            result = "📋 倒数日概览:\n"
            today = datetime.now()
            
            for cd in sorted(countdowns, key=lambda x: x["target_date"]):
                target_date = datetime.strptime(cd["target_date"], "%Y-%m-%d")
                days_left = self._calculate_days_left(target_date)
                
                if days_left >= 0:  # 只显示未来的事件
                    icon = "🔔" if days_left <= cd["remind_days"] else "⏳"
                    result += f"{icon} {cd['name']}: 剩余{days_left}天\n"
            
            yield event.plain_result(result.strip())

    @filter.command("set_remind")
    async def set_remind_days(self, event: AstrMessageEvent, name: str, days: int):
        """设置提前提醒天数
        用法: /set_remind 事件名称 天数
        示例: /set_remind 生日 7
        """
        if days < 0 or days > 365:
            yield event.plain_result("提醒天数应在0-365之间")
            return

        countdowns = await self._get_countdowns(event)
        
        for cd in countdowns:
            if cd["name"] == name:
                cd["remind_days"] = days
                if await self._save_countdowns(event, countdowns):
                    yield event.plain_result(f"✅ 已设置「{name}」提前{days}天提醒")
                else:
                    yield event.plain_result("设置失败，请稍后重试")
                return
        
        yield event.plain_result(f"未找到名为「{name}」的倒数日")

    @filter.command("countdown_help")
    async def show_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = """
📅 倒数日插件使用说明：

/add_countdown <事件名称> <日期> - 添加倒数日
  示例: /add_countdown 生日 12-25
  示例: /add_countdown 春节 2025-01-29

/del_countdown <名称或序号> - 删除倒数日
  示例: /del_countdown 生日 或 /del_countdown 1

/list_countdown - 列出所有倒数日

/countdown [事件名称] - 查看倒数日详情
  示例: /countdown 或 /countdown 生日

/set_remind <事件名称> <天数> - 设置提前提醒天数
  示例: /set_remind 生日 7

/countdown_help - 显示此帮助信息
        """
        yield event.plain_result(help_text.strip())

    async def terminate(self):
        """插件卸载时调用"""
        logger.info("倒数日插件已卸载")