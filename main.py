from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp
import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import asyncio

@register("countdown", "Kihana2077", "智能倒数日管理插件", "0.0.1", "https://github.com/your-repo")
class CountdownPlugin(Star):
    def __init__(self, context: Context, config: Dict):
        super().__init__(context)
        self.config = config
        self.data_file = self.get_data_file_path(context)
        self.countdowns = {}  # 内存中存储数据
        self.load_data()
        logger.info("倒数日插件已初始化")
        
        # 启动定时提醒任务
        asyncio.create_task(self.reminder_task())

    def get_data_file_path(self, context: Context) -> str:
        """获取数据文件路径"""
        try:
            # 尝试不同的方法获取数据目录
            if hasattr(context, 'get_data_dir'):
                data_dir = context.get_data_dir()
            elif hasattr(context, 'data_dir'):
                data_dir = context.data_dir
            elif hasattr(context, 'get_plugin_data_dir'):
                data_dir = context.get_plugin_data_dir()
            else:
                # 如果以上方法都不可用，使用默认路径
                data_dir = os.path.join(os.path.dirname(__file__), "data")
            
            os.makedirs(data_dir, exist_ok=True)
            return os.path.join(data_dir, "countdowns.json")
        except Exception as e:
            logger.error(f"获取数据目录失败: {e}")
            # 使用当前目录作为备选
            return "countdowns.json"

    def load_data(self):
        """从文件加载数据"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self.countdowns = json.load(f)
                logger.info(f"数据加载成功，共 {sum(len(v) for v in self.countdowns.values())} 条记录")
            else:
                self.countdowns = {}
                logger.info("创建新的数据文件")
        except Exception as e:
            logger.error(f"加载数据失败: {e}")
            self.countdowns = {}

    def save_data(self):
        """保存数据到文件"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.countdowns, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存数据失败: {e}")

    def get_user_key(self, user_id: str, group_id: str = "") -> str:
        """生成用户存储键"""
        return f"{user_id}_{group_id}" if group_id else user_id

    def get_next_id(self, user_key: str) -> int:
        """获取下一个ID"""
        if user_key not in self.countdowns:
            return 1
        return max([cd['id'] for cd in self.countdowns[user_key]], default=0) + 1

    @filter.command("添加倒数日")
    async def add_countdown_command(self, event: AstrMessageEvent, name: str, target_date: str, remark: str = ""):
        '''添加新的倒数日'''
        # 检查权限
        if self.config.get("admin_only", False):
            if not event.is_admin():
                yield event.plain_result("❌ 只有管理员可以添加倒数日")
                return
        
        user_id = event.get_sender_id()
        group_id = event.get_group_id() or ""
        user_key = self.get_user_key(user_id, group_id)
        
        # 验证并添加倒数日
        success, result = await self.add_countdown(user_key, name, target_date, remark)
        
        if success:
            yield event.plain_result(f"✅ 已添加倒数日：{name}")
            yield event.plain_result(f"📅 目标日期：{target_date}")
            if remark:
                yield event.plain_result(f"📝 备注：{remark}")
        else:
            yield event.plain_result(f"❌ {result}")

    @filter.command("倒数日列表")
    async def list_countdowns_command(self, event: AstrMessageEvent):
        '''查看我的倒数日列表'''
        user_id = event.get_sender_id()
        group_id = event.get_group_id() or ""
        user_key = self.get_user_key(user_id, group_id)
        
        countdowns = self.get_user_countdowns(user_key)
        
        if not countdowns:
            yield event.plain_result("📭 您还没有添加任何倒数日")
            yield event.plain_result("使用「/添加倒数日 名称 日期」来创建第一个倒数日")
            return
        
        response = "📅 您的倒数日列表：\n\n"
        for cd in countdowns:
            status_emoji = "⏳" if cd['days_left'] > 0 else "✅"
            response += f"{cd['id']}. {status_emoji} {cd['name']}\n"
            response += f"   日期：{cd['target_date']} | {cd['status']}\n"
            if cd['remark']:
                response += f"   备注：{cd['remark']}\n"
            response += "\n"
        
        response += "\n💡 使用「/删除倒数日 ID」来删除指定倒数日"
        
        yield event.plain_result(response)

    @filter.command("删除倒数日")
    async def delete_countdown_command(self, event: AstrMessageEvent, countdown_id: int):
        '''删除指定ID的倒数日'''
        # 检查权限
        if self.config.get("admin_only", False):
            if not event.is_admin():
                yield event.plain_result("❌ 只有管理员可以删除倒数日")
                return
        
        user_id = event.get_sender_id()
        group_id = event.get_group_id() or ""
        user_key = self.get_user_key(user_id, group_id)
        
        success = self.delete_countdown(user_key, countdown_id)
        
        if success:
            yield event.plain_result(f"✅ 已删除倒数日 #{countdown_id}")
        else:
            yield event.plain_result("❌ 删除失败，请检查ID是否正确或您是否有权限删除")

    @filter.command("最近倒数日")
    async def recent_countdowns_command(self, event: AstrMessageEvent, days: int = 30):
        '''查看最近N天内的倒数日'''
        user_id = event.get_sender_id()
        group_id = event.get_group_id() or ""
        user_key = self.get_user_key(user_id, group_id)
        
        if days <= 0:
            yield event.plain_result("❌ 天数必须大于0")
            return
        
        countdowns = self.get_recent_countdowns(user_key, days)
        
        if not countdowns:
            yield event.plain_result(f"📭 最近{days}天内没有倒数日")
            return
        
        response = f"⏰ 最近{days}天内的倒数日：\n\n"
        for cd in countdowns:
            emoji = "🎯" if cd['days_left'] > 0 else "🎉"
            response += f"{emoji} {cd['name']} - {cd['target_date']} ({cd['status']})\n"
            if cd['remark']:
                response += f"   📝 {cd['remark']}\n"
        
        yield event.plain_result(response)

    @filter.command("倒数日帮助")
    async def help_command(self, event: AstrMessageEvent):
        '''显示倒数日插件帮助信息'''
        help_text = """
📅 倒数日插件使用指南：

**命令列表：**
• /添加倒数日 名称 日期(YYYY-MM-DD) [备注]
• /倒数日列表 - 查看所有倒数日
• /删除倒数日 ID - 删除指定倒数日
• /最近倒数日 [天数] - 查看近期倒数日

**自然语言查询：**
• "距离生日还有几天"
• "考试是什么时候"
• "查看我的倒数日"

**示例：**
• /添加倒数日 生日 2024-12-31
• 距离期末考试还有几天
• /删除倒数日 1

💡 提示：日期格式为 YYYY-MM-DD
        """
        yield event.plain_result(help_text)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_natural_language(self, event: AstrMessageEvent):
        '''处理自然语言查询'''
        # 忽略命令消息
        if event.message_str.startswith('/'):
            return
            
        message = event.message_str.lower().strip()
        user_id = event.get_sender_id()
        group_id = event.get_group_id() or ""
        user_key = self.get_user_key(user_id, group_id)
        
        # 匹配各种查询模式
        patterns = [
            (r'距离(.+)还有几天', self.handle_days_query),
            (r'(.+)是什么时候', self.handle_date_query),
            (r'查看我的倒数日', self.handle_list_query),
            (r'倒数日帮助', self.handle_help_query),
        ]
        
        for pattern, handler in patterns:
            match = re.search(pattern, message)
            if match:
                # 调用对应的处理函数
                await handler(event, user_key, match.group(1) if match.lastindex else "")
                event.stop_event()  # 阻止其他插件处理
                return

    async def handle_days_query(self, event: AstrMessageEvent, user_key: str, name: str):
        '''处理"距离XXX还有几天"的查询'''
        countdown = self.find_countdown_by_name(user_key, name)
        
        if countdown:
            if countdown['days_left'] > 0:
                response = f"📅 距离「{name}」还有 {countdown['days_left']} 天\n"
                response += f"🗓️ 日期：{countdown['target_date']}"
                if countdown['remark']:
                    response += f"\n📝 备注：{countdown['remark']}"
                yield event.plain_result(response)
            else:
                yield event.plain_result(f"🎉 「{name}」已经过去 {-countdown['days_left']} 天了！")
        else:
            yield event.plain_result(f"❓ 没有找到名为「{name}」的倒数日")
            yield event.plain_result("💡 使用「/添加倒数日 名称 日期」来创建")

    async def handle_date_query(self, event: AstrMessageEvent, user_key: str, name: str):
        '''处理"XXX是什么时候"的查询'''
        countdown = self.find_countdown_by_name(user_key, name)
        
        if countdown:
            response = f"📅 「{name}」的日期是：{countdown['target_date']}\n"
            if countdown['days_left'] > 0:
                response += f"⏳ 还有 {countdown['days_left']} 天"
            else:
                response += f"🎉 已经过去 {-countdown['days_left']} 天了！"
            if countdown['remark']:
                response += f"\n📝 备注：{countdown['remark']}"
            yield event.plain_result(response)
        else:
            yield event.plain_result(f"❓ 没有找到名为「{name}」的倒数日")
            yield event.plain_result("💡 使用「/添加倒数日 名称 日期」来创建")

    async def handle_list_query(self, event: AstrMessageEvent, user_key: str, _=None):
        '''处理"查看我的倒数日"的查询'''
        countdowns = self.get_user_countdowns(user_key)
        
        if not countdowns:
            yield event.plain_result("📭 您还没有添加任何倒数日")
            yield event.plain_result("使用「/添加倒数日 名称 日期」来创建第一个倒数日")
            return
        
        response = "📅 您的倒数日列表：\n\n"
        for cd in countdowns:
            status_emoji = "⏳" if cd['days_left'] > 0 else "✅"
            response += f"{cd['id']}. {status_emoji} {cd['name']}\n"
            response += f"   日期：{cd['target_date']} | {cd['status']}\n"
            if cd['remark']:
                response += f"   备注：{cd['remark']}\n"
            response += "\n"
        
        yield event.plain_result(response)

    async def handle_help_query(self, event: AstrMessageEvent, user_key: str, _=None):
        '''处理"帮助"的查询'''
        help_text = """
📅 倒数日插件使用指南：

**命令列表：**
• /添加倒数日 名称 日期(YYYY-MM-DD) [备注]
• /倒数日列表 - 查看所有倒数日
• /删除倒数日 ID - 删除指定倒数日
• /最近倒数日 [天数] - 查看近期倒数日

**自然语言查询：**
• "距离生日还有几天"
• "考试是什么时候"
• "查看我的倒数日"

**示例：**
• /添加倒数日 生日 2024-12-31
• 距离期末考试还有几天
• /删除倒数日 1

💡 提示：日期格式为 YYYY-MM-DD
        """
        yield event.plain_result(help_text)

    # 数据操作方法
    async def add_countdown(self, user_key: str, name: str, date_str: str, remark: str = "") -> tuple:
        """添加倒数日"""
        try:
            # 验证日期格式
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            today = datetime.now().date()
            
            if target_date < today:
                return False, "目标日期不能是过去的时间"
            
            # 检查数量限制
            max_count = self.config.get("max_countdowns", 50)
            current_count = len(self.get_user_countdowns(user_key))
            
            if current_count >= max_count:
                return False, f"已达到最大倒数日数量限制({max_count}个)"
            
            # 添加到内存
            if user_key not in self.countdowns:
                self.countdowns[user_key] = []
            
            countdown_id = self.get_next_id(user_key)
            
            countdown = {
                'id': countdown_id,
                'name': name,
                'target_date': date_str,
                'created_date': today.strftime("%Y-%m-%d"),
                'remark': remark,
                'notified_days': []
            }
            
            self.countdowns[user_key].append(countdown)
            self.save_data()  # 保存到文件
            
            return True, "添加成功"
            
        except ValueError:
            return False, "日期格式错误，请使用 YYYY-MM-DD 格式"
        except Exception as e:
            logger.error(f"添加倒数日失败: {e}")
            return False, "添加失败，请稍后重试"

    def get_user_countdowns(self, user_key: str) -> List[Dict[str, Any]]:
        """获取用户的倒数日列表"""
        if user_key not in self.countdowns:
            return []
        
        result = []
        for cd in self.countdowns[user_key]:
            target_date = datetime.strptime(cd['target_date'], "%Y-%m-%d").date()
            today = datetime.now().date()
            days_diff = (target_date - today).days
            
            status = "已过期" if days_diff < 0 else f"剩余{days_diff}天"
            
            result.append({
                'id': cd['id'],
                'name': cd['name'],
                'target_date': cd['target_date'],
                'days_left': days_diff,
                'remark': cd['remark'],
                'status': status
            })
        
        # 按日期排序
        result.sort(key=lambda x: x['target_date'])
        return result

    def get_recent_countdowns(self, user_key: str, days: int) -> List[Dict[str, Any]]:
        """获取最近N天内的倒数日"""
        all_countdowns = self.get_user_countdowns(user_key)
        result = []
        
        for cd in all_countdowns:
            if 0 <= cd['days_left'] <= days:
                result.append(cd)
        
        return result

    def find_countdown_by_name(self, user_key: str, name: str) -> Optional[Dict[str, Any]]:
        """根据名称查找倒数日"""
        countdowns = self.get_user_countdowns(user_key)
        
        for cd in countdowns:
            if name in cd['name']:
                return cd
        
        return None

    def delete_countdown(self, user_key: str, countdown_id: int) -> bool:
        """删除倒数日"""
        if user_key not in self.countdowns:
            return False
        
        # 查找并删除
        for i, cd in enumerate(self.countdowns[user_key]):
            if cd['id'] == countdown_id:
                del self.countdowns[user_key][i]
                self.save_data()  # 保存到文件
                return True
        
        return False

    async def reminder_task(self):
        """定时提醒任务"""
        while True:
            try:
                if self.config.get("enable_reminders", True):
                    await self.check_reminders()
                await asyncio.sleep(3600)  # 每小时检查一次
            except Exception as e:
                logger.error(f"提醒任务出错: {e}")
                await asyncio.sleep(300)  # 出错后等待5分钟重试

    async def check_reminders(self):
        """检查需要发送的提醒"""
        try:
            reminder_days = self.config.get("reminder_days", [7, 3, 1])
            today = datetime.now().date()
            
            for user_key, countdown_list in self.countdowns.items():
                for cd in countdown_list:
                    target_date = datetime.strptime(cd['target_date'], "%Y-%m-%d").date()
                    days_left = (target_date - today).days
                    
                    if days_left in reminder_days:
                        notified = cd.get('notified_days', [])
                        if str(days_left) not in notified:
                            await self.send_reminder(user_key, cd, days_left)
                            # 更新已通知天数
                            cd['notified_days'] = notified + [str(days_left)]
                            self.save_data()  # 保存到文件
                            
        except Exception as e:
            logger.error(f"检查提醒失败: {e}")

    async def send_reminder(self, user_key: str, countdown: Dict, days_left: int):
        """发送提醒消息"""
        try:
            # 解析用户ID和群ID
            parts = user_key.split('_')
            if len(parts) == 2:
                user_id, group_id = parts
            else:
                user_id = parts[0]
                group_id = ""
            
            message_template = self.config.get("reminder_message", 
                "📢 提醒：距离「{name}」还有 {days} 天！")
            
            message = message_template.format(
                name=countdown['name'],
                days=days_left,
                date=countdown['target_date']
            )
            
            # 构建消息链
            chains = [Comp.Plain(message)]
            if countdown['remark']:
                chains.append(Comp.Plain(f"\n📝 {countdown['remark']}"))
            
            # 发送消息到用户
            try:
                if group_id:
                    # 如果是群聊，发送到群
                    await self.ctx.send_message_to_group(group_id, chains)
                else:
                    # 如果是私聊，发送给用户
                    await self.ctx.send_message_to_user(user_id, chains)
            except Exception as e:
                logger.error(f"发送提醒消息失败: {e}")
                
        except Exception as e:
            logger.error(f"发送提醒失败: {e}")

    async def terminate(self):
        '''插件卸载时调用'''
        self.save_data()  # 保存数据
        logger.info("倒数日插件已卸载")



