from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import sqlite3
import os
from datetime import datetime
from typing import Dict, List, Any

@register("countdown", "Kihana2077", "倒数日插件", "0.1", "https://github.com/kihana2077/astrbot-plugin-countdown")
class CountdownPlugin(Star):
    def __init__(self, context: Context, config: Dict):
        super().__init__(context)
        self.config = config
        self.db_path = os.path.join(context.data_dir, self.config.get("database", {}).get("filename", "countdown.db"))
        self.init_db()
        logger.info("倒数日插件已初始化")
    
    def init_db(self):
        """初始化数据库"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS countdowns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        target_date TEXT NOT NULL,
                        created_date TEXT NOT NULL,
                        remark TEXT DEFAULT '',
                        user_id TEXT NOT NULL
                    )
                """)
                conn.commit()
            logger.info("数据库初始化成功")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
    
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
                rows = cursor.fetchall()
                
                result = []
                for row in rows:
                    target_date = datetime.strptime(row['target_date'], "%Y-%m-%d")
                    today = datetime.now().date()
                    days_diff = (target_date.date() - today).days
                    
                    result.append({
                        'id': row['id'],
                        'name': row['name'],
                        'target_date': row['target_date'],
                        'days_left': days_diff,
                        'remark': row['remark'],
                        'status': '已过期' if days_diff < 0 else f'剩余{days_diff}天'
                    })
                
                return result
        except Exception as e:
            logger.error(f"获取倒数日列表失败: {e}")
            return []
    
    def add_countdown(self, user_id: str, name: str, target_date: str, remark: str = "") -> bool:
        """添加倒数日"""
        try:
            # 验证日期格式
            datetime.strptime(target_date, "%Y-%m-%d")
            
            max_count = self.config.get("features", {}).get("max_countdowns_per_user", 20)
            current_count = len(self.get_user_countdowns(user_id))
            
            if current_count >= max_count:
                return False, f"已达到最大倒数日数量限制({max_count}个)"
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO countdowns (name, target_date, created_date, remark, user_id) VALUES (?, ?, ?, ?, ?)",
                    (name, target_date, datetime.now().strftime("%Y-%m-%d"), remark, user_id)
                )
                conn.commit()
            return True, "添加成功"
        except ValueError:
            return False, "日期格式错误，请使用 YYYY-MM-DD 格式"
        except Exception as e:
            logger.error(f"添加倒数日失败: {e}")
            return False, "添加失败，请稍后重试"
    
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

    # 主要命令处理函数
    @filter.command("addcountdown")
    async def add_countdown_command(self, event: AstrMessageEvent, name: str, target_date: str, remark: str = ""):
        '''添加倒数日 - 用法: /addcountdown 名称 日期 [备注]'''
        user_id = event.get_sender_id()
        
        # 检查群聊使用权限
        if event.get_group_id() and not self.config.get("permissions", {}).get("allow_group", True):
            yield event.plain_result("群聊中暂不支持使用倒数日功能")
            return
        
        success, message = self.add_countdown(user_id, name, target_date, remark)
        if success:
            yield event.plain_result(f"✅ 已添加倒数日: {name} - {target_date}")
            if remark:
                yield event.plain_result(f"📝 备注: {remark}")
        else:
            yield event.plain_result(f"❌ {message}")
    
    @filter.command("listcountdown")
    async def list_countdown_command(self, event: AstrMessageEvent):
        '''列出所有倒数日'''
        user_id = event.get_sender_id()
        countdowns = self.get_user_countdowns(user_id)
        
        if not countdowns:
            yield event.plain_result("📭 您还没有添加任何倒数日")
            yield event.plain_result("使用 /addcountdown 名称 日期 来添加倒数日")
            return
        
        response = f"📅 您的倒数日列表 (共{len(countdowns)}个):\n\n"
        for cd in countdowns:
            emoji = "⏳" if cd['days_left'] > 0 else "✅"
            response += f"{emoji} {cd['id']}. {cd['name']} - {cd['target_date']} ({cd['status']})\n"
            if cd['remark']:
                response += f"   📝 {cd['remark']}\n"
        
        # 如果消息太长，分开发送
        if len(response) > 500:
            parts = [response[i:i+500] for i in range(0, len(response), 500)]
            for part in parts:
                yield event.plain_result(part)
        else:
            yield event.plain_result(response)
    
    @filter.command("deletecountdown")
    async def delete_countdown_command(self, event: AstrMessageEvent, countdown_id: int):
        '''删除倒数日 - 用法: /deletecountdown ID'''
        user_id = event.get_sender_id()
        
        # 检查管理员权限
        if self.config.get("permissions", {}).get("admin_only_delete", False):
            if not event.is_admin():
                yield event.plain_result("❌ 只有管理员可以删除倒数日")
                return
        
        success = self.delete_countdown(user_id, countdown_id)
        if success:
            yield event.plain_result(f"✅ 已删除倒数日 #{countdown_id}")
        else:
            yield event.plain_result("❌ 删除失败，请检查ID是否正确")
    
    @filter.command("countdownhelp")
    async def help_command(self, event: AstrMessageEvent):
        '''显示倒数日插件帮助信息'''
        help_text = """
📅 倒数日插件使用说明:

**基本命令:**
/addcountdown <名称> <日期YYYY-MM-DD> [备注] - 添加倒数日
/listcountdown - 显示所有倒数日  
/deletecountdown <ID> - 删除指定倒数日
/countdownhelp - 显示帮助信息

**示例:**
/addcountdown 生日 2025-12-31
/addcountdown 考试 2024-06-15 重要考试
/listcountdown
/deletecountdown 1

**说明:**
- 日期格式: YYYY-MM-DD (如: 2024-12-31)
- 每个用户最多可添加 {} 个倒数日
        """.format(self.config.get("features", {}).get("max_countdowns_per_user", 20))
        
        yield event.plain_result(help_text)
    
    async def terminate(self):
        '''插件卸载时调用'''
        logger.info("倒数日插件已卸载")