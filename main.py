from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp
import sqlite3
import os
import re
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import asyncio

@register("countdown", "Kihana2077", "智能倒数日管理插件", "0.0.1", "https://github.com/your-repo")
class CountdownPlugin(Star):
    def __init__(self, context: Context, config: Dict):
        super().__init__(context)
        self.config = config
        self.db_path = os.path.join(context.data_dir, "countdown.db")
        self.init_db()
        logger.info("倒数日插件已初始化")
        
        # 启动定时提醒任务
        asyncio.create_task(self.reminder_task())

    def init_db(self):
        """初始化数据库"""
        try:
            with sql极速电竞APP下载ite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS countdowns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        target_date TEXT NOT NULL,
                        created_date TEXT NOT NULL,
                        remark TEXT DEFAULT '',
                        user_id TEXT NOT NULL,
                        group_id TEXT DEFAULT '',
                        notified_days TEXT DEFAULT ''
                    )
                """)
                conn.commit()
            logger.info("数据库初始化成功")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")

    @filter.command("添加倒数日")
    async def add_countdown_command(self, event: AstrMessageEvent):
        '''添加新的倒数日 - 格式：添加倒数日 名称 日期(YYYY-MM-DD) [备注]'''
        # 检查权限
        if self.config.get("admin_only", False):
            if not event.is_admin():
                yield event.plain_result("❌ 只有管理员可以添加倒数日")
                return
        
        # 检查群聊权限
        if event.get_group_id() and not self.config.get("enable_group_chat", True):
            yield event.plain_result("❌ 群聊中暂不支持使用倒数日功能")
            return
        
        # 检查私聊权限
        if not event.get_group_id() and not self.config.get("enable_private_chat", True):
            yield event.plain_result("❌ 私聊中暂不支持使用倒数日功能")
            return
        
        user_id = event.get_sender_id()
        group_id = event.get_group_id() or ""
        message = event.message_str.strip()
        
        # 解析消息内容
        parts = message.split()
        if len(parts) < 3:
            yield event.plain_result("❌ 格式错误！正确格式：添加倒数日 名称 日期(YYYY-MM-DD) [备注]")
            return
        
        name = parts[1]
        date_str = parts[2]
        remark = " ".join(parts[3:]) if len(parts) > 3 else ""
        
        # 验证并添加倒数日
        success, result = await self.add_countdown(user_id, group_id, name, date_str, remark)
        
        if success:
            yield event.plain_result(f"✅ 已添加倒数日：{name}\n📅 目标日期：{date_str}")
            if remark:
                yield event.plain_result(f"📝 备注：{remark}")
        else:
            yield event.plain_result(f"❌ {result}")

    @filter.command("倒数日列表")
    async def list_countdowns_command(self, event: AstrMessageEvent):
        '''查看我的倒数日列表'''
        user_id = event.get_sender_id()
        countdowns = self.get_user_countdowns(user_id)
        
        if not countdowns:
            yield event.plain_result("📭 您还没有添加任何倒数日")
            yield event.plain_result("使用「添加倒数日 名称 日期」来创建第一个倒数日")
            return
        
        # 构建消息链
        chains = []
        chains.append(Comp.Plain("📅 您的倒数日列表：\n\n"))
        
        for i, cd in enumerate(countdowns, 1):
            status_emoji = "⏳" if cd['days_left'] > 0 else "✅"
            chains.append(Comp.Plain(f"{i}. {status_emoji} {cd['name']}\n"))
            chains.append(Comp.Plain(f"   日期：{cd['target_date']} | {cd['status']}\n"))
            if cd['remark']:
                chains.append(Comp.Plain(f"   备注：{cd['remark']}\n"))
            chains.append(Comp.Plain("\n"))
        
        chains.append(Comp.Plain(f"\n💡 使用「删除倒数日 ID」来删除指定倒数日"))
        
        yield event.chain_result(chains)

    @filter.command("删除倒数日")
    async def delete_countdown_command(self, event: AstrMessageEvent):
        '''删除指定ID的倒数日'''
        # 检查权限
        if self.config.get("admin_only", False):
            if not event.is_admin():
                yield event.plain_result("❌ 只有管理员可以删除倒数日")
                return
        
        user_id = event.get_sender_id()
        message = event.message_str.strip()
        
        # 解析消息内容
        parts = message.split()
        if len(parts) < 2:
            yield event.plain_result("❌ 格式错误！正确格式：删除倒数日 ID")
            return
        
        try:
            countdown_id = int(parts[1])
        except ValueError:
            yield event.plain_result("❌ ID必须是数字")
            return
        
        success = self.delete_countdown(user_id, countdown_id)
        
        if success:
            yield event.plain_result(f"✅ 已删除倒数日 #{countdown_id}")
        else:
            yield event.plain_result("❌ 删除失败，请检查ID是否正确或您是否有权限删除")

    @filter.command("最近倒数日")
    async def recent_countdowns_command(self, event: AstrMessageEvent):
        '''查看最近N天内的倒数日'''
        user_id = event.get_sender_id()
        message = event.message_str.strip()
        
        # 解析消息内容
        parts = message.split()
        days = 30  # 默认30天
        
        if len(parts) > 1:
            try:
                days = int(parts[1])
            except ValueError:
                yield event.plain_result("❌ 天数必须是数字")
                return
        
        countdowns = self.get_recent_countdowns(user_id, days)
        
        if not countdowns:
            yield event.plain_result(f"📭 最近{days}天内没有倒数日")
            return
        
        chains = [Comp.Plain(f"⏰ 最近{days}天内的倒数日：\n\n")]
        
        for cd in countdowns:
            emoji = "🎯" if cd['days_left'] > 0 else "🎉"
            chains.append(Comp.Plain(f"{emoji} {cd['name']} - {cd['target_date']} ({cd['status']})\n"))
            if cd['remark']:
                chains.append(Comp.Plain(f"   📝 {cd['remark']}\n"))
        
        yield event.chain_result(chains)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_countdown_query(self, event: AstrMessageEvent):
        '''处理自然语言查询'''
        try:
            message = event.message_str.lower().strip()
            
            # 匹配各种查询模式
            patterns = [
                (r'距离(.+)还有几天', self.handle_days_query),
                (r'(.+)是什么时候', self.handle_date_query),
                (r'倒数日帮助', self.show_help),
                (r'帮助倒数日', self.show_help),
            ]
            
            for pattern, handler in patterns:
                match = re.search(pattern, message)
                if match:
                    # 直接调用处理函数并传递 event 参数
                    await handler(event, match.group(1))
                    event.stop_event()  # 阻止其他插件处理
                    return
        except Exception as e:
            logger.error(f"处理自然语言查询失败: {e}")

    async def handle_days_query(self, event: AstrMessageEvent, name: str):
        '''处理"距离XXX还有几天"的查询'''
        user_id = event.get_sender_id()
        countdown = self.find_countdown_by_name(user_id, name)
        
        if countdown:
            if countdown['days_left'] > 0:
                yield event.plain_result(f"📅 距离「{name}」还有 {countdown['days_left']} 天")
                yield event.plain_result(f"🗓️ 日期：{countdown['target_date']}")
            else:
                yield event.plain_result(f"🎉 「{name}」已经过去 {-countdown['days_left']} 天了！")
        else:
            yield event.plain_result(f"❓ 没有找到名为「{name}」的倒数日")
            yield event.plain_result("💡 使用「添加倒数日 名称 日期」来创建")

    async def handle_date_query(self, event: AstrMessageEvent, name: str):
        '''处理"XXX是什么时候"的查询'''
        user_id = event.get_sender_id()
        countdown = self.find_countdown_by_name(user_id, name)
        
        if countdown:
            yield event.plain_result(f"📅 「{name}」的日期是：{countdown['target_date']}")
            if countdown['days_left'] > 0:
                yield event.plain_result(f"⏳ 还有 {countdown['days_left']} 天")
            else:
                yield event.plain_result(f"🎉 已经过去 {-countdown['days_left']} 天了！")
        else:
            yield event.plain_result(f"❓ 没有找到名为「{name}」的倒数日")

    async def show_help(self, event: AstrMessageEvent, _=None):
        '''显示帮助信息'''
        help_text = """
📅 倒数日插件使用指南：

**命令列表：**
• 添加倒数日 名称 日期(YYYY-MM-DD) [备注]
• 倒数日列表 - 查看所有倒数日
• 删除倒数日 ID - 删除指定倒数日
• 最近倒数日 [天数] - 查看近期倒数日

**自然语言查询：**
• "距离生日还有几天"
• "考试是什么时候"
• "倒数日帮助"

**示例：**
• 添加倒数日 生日 2024-12-31
• 距离期末考试还有几天
• 删除倒数日 1

💡 提示：日期格式为 YYYY-MM-DD，如：2024-12-31
        """
        yield event.plain_result(help_text)

    # 数据库操作方法
    async def add_countdown(self, user_id: str, group_id: str, name: str, date_str: str, remark: str = "") -> tuple:
        """添加倒数日"""
        try:
            # 验证日期格式
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            today = datetime.now().date()
            
            if target_date < today:
                return False, "目标日期不能是过去的时间"
            
            # 检查数量限制
            max_count = self.config.get("max_countdowns", 50)
            current_count = len(self.get_user_countdowns(user_id))
            
            if current_count >= max_count:
                return False, f"已达到最大倒数日数量限制({max_count}个)"
            
            # 添加到数据库
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO countdowns (name, target_date, created_date, remark, user_id, group_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (name, date_str, today.strftime("%Y-%m-%d"), remark, user_id, group_id))
                conn.commit()
            
            return True, "添加成功"
            
        except ValueError:
            return False, "日期格式错误，请使用 YYYY-MM-DD 格式"
        except Exception as e:
            logger.error(f"添加倒数日失败: {e}")
            return False, "添加失败，请稍后重试"

    def get_user_countdowns(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户的倒数日列表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM countdowns WHERE user_id = ? ORDER BY target_date",
                    (user_id,)
                )
                return self._process_countdown_rows(cursor.fetchall())
        except Exception as e:
            logger.error(f"获取倒数日列表失败: {e}")
            return []

    def get_recent_countdowns(self, user_id: str, days: int) -> List[Dict[str, Any]]:
        """获取最近N天内的倒数日"""
        try:
            target_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM countdowns 
                    WHERE user_id = ? AND target_date <= ? AND target_date >= date('now')
                    ORDER BY target_date
                """, (user_id, target_date))
                return self._process_countdown_rows(cursor.fetchall())
        except Exception as e:
            logger.error(f"获取最近倒数日失败: {e}")
            return []

    def find_countdown_by_name(self, user_id: str, name: str) -> Optional[Dict[str, Any]]:
        """根据名称查找倒数日"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM countdowns WHERE user_id = ? AND name LIKE ?",
                    (user_id, f"%{name}%")
                )
                rows = self._process_countdown_rows(cursor.fetchall())
                return rows[0] if rows else None
        except Exception as e:
            logger.error(f"查找倒数日失败: {e}")
            return None

    def delete_countdown(self, user_id: str, countdown_id: int) -> bool:
        """删除倒数日"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM countdowns WHERE id = ? AND user_id = ?",
                    (countdown_id, user_id)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除倒数日失败: {e}")
            return False

    def _process_countdown_rows(self, rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
        """处理数据库行数据"""
        result = []
        for row in rows:
            target_date = datetime.strptime(row['target_date'], "%Y-%m-%d").date()
            today = datetime.now().date()
            days_diff = (target_date - today).days
            
            status = "已过期" if days_diff < 0 else f"剩余{days_diff}天"
            
            result.append({
                'id': row['id'],
                'name': row['name'],
                'target_date': row['target_date'],
                'days_left': days_diff,
                'remark': row['remark'],
                'status': status
            })
        return result

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
            
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM countdowns 
                    WHERE target_date >= date('now')
                """)
                
                for row in cursor.fetchall():
                    target_date = datetime.strptime(row['target_date'], "%Y-%m-%d").date()
                    days_left = (target_date - today).days
                    
                    if days_left in reminder_days:
                        notified = row['notified_days'] or ""
                        if str(days_left) not in notified.split(','):
                            await self.send_reminder(row, days_left)
                            # 更新已通知天数
                            new_notified = f"{notified},{days_left}" if notified else str(days_left)
                            cursor.execute(
                                "UPDATE countdowns SET notified_days = ? WHERE id = ?",
                                (new_notified, row['id'])
                            )
                            conn.commit()
                            
        except Exception as e:
            logger.error(f"检查提醒失败: {e}")

    async def send_reminder(self, countdown: sqlite3.Row, days_left: int):
        """发送提醒消息"""
        try:
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
            
            # 发送消息
            await self.context.send_message(
                countdown['user_id'],  # 这里简化处理，实际应该使用 unified_msg_origin
                chains
            )
            
        except Exception as e:
            logger.error(f"发送提醒失败: {e}")

    async def terminate(self):
        '''插件卸载时调用'''
        logger.info("倒数日插件已卸载")