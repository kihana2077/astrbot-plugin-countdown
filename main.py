from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import sqlite3
import os
from datetime import datetime

@register("countdown", "author", "倒数日插件", "1.0.0", "https://github.com/your-repo")
class CountdownPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.db_path = os.path.join(context.data_dir, "countdown.db")
        self.init_db()
        logger.info("倒数日插件已初始化")
    
    def init_db(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS countdowns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    target_date TEXT NOT NULL,
                    created_date TEXT NOT NULL,
                    user_id TEXT
                )
            """)
            conn.commit()
    
    def add_countdown(self, name: str, target_date: str, user_id: str) -> bool:
        """添加倒数日"""
        try:
            # 验证日期格式
            datetime.strptime(target_date, "%Y-%m-%d")
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO countdowns (name, target_date, created_date, user_id) VALUES (?, ?, ?, ?)",
                    (name, target_date, datetime.now().strftime("%Y-%m-%d"), user_id)
                )
                conn.commit()
            return True
        except ValueError:
            return False
        except Exception as e:
            logger.error(f"添加倒数日失败: {e}")
            return False
    
    def list_countdowns(self, user_id: str) -> list:
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
                    today = datetime.now()
                    days_diff = (target_date - today).days
                    
                    result.append({
                        'id': row['id'],
                        'name': row['name'],
                        'target_date': row['target_date'],
                        'days_left': days_diff
                    })
                
                return result
        except Exception as e:
            logger.error(f"获取倒数日列表失败: {e}")
            return []
    
    @filter.command("addcountdown")
    async def add_countdown_command(self, event: AstrMessageEvent):
        '''添加倒数日'''
        args = event.message_str.split()
        if len(args) < 3:
            yield event.plain_result("用法: /addcountdown <名称> <日期YYYY-MM-DD>")
            return
        
        name = args[1]
        date_str = args[2]
        user_id = event.get_sender_id()
        
        if self.add_countdown(name, date_str, user_id):
            yield event.plain_result(f"已添加倒数日: {name} - {date_str}")
        else:
            yield event.plain_result("添加失败，请检查日期格式(YYYY-MM-DD)")
    
    @filter.command("listcountdown")
    async def list_countdown_command(self, event: AstrMessageEvent):
        '''列出倒数日'''
        user_id = event.get_sender_id()
        countdowns = self.list_countdowns(user_id)
        
        if not countdowns:
            yield event.plain_result("您还没有添加任何倒数日")
            return
        
        response = "您的倒数日列表:\n"
        for cd in countdowns:
            status = "已过期" if cd['days_left'] < 0 else f"剩余{cd['days_left']}天"
            response += f"{cd['id']}. {cd['name']} - {cd['target_date']} ({status})\n"
        
        yield event.plain_result(response)
    
    @filter.command("deletecountdown")
    async def delete_countdown_command(self, event: AstrMessageEvent):
        '''删除倒数日'''
        args = event.message_str.split()
        if len(args) < 2:
            yield event.plain_result("用法: /deletecountdown <ID>")
            return
        
        try:
            cd_id = int(args[1])
            user_id = event.get_sender_id()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM countdowns WHERE id = ? AND user_id = ?",
                    (cd_id, user_id)
                )
                conn.commit()
                
                if cursor.rowcount > 0:
                    yield event.plain_result(f"已删除倒数日 #{cd_id}")
                else:
                    yield event.plain_result("删除失败，请检查ID是否正确")
        except ValueError:
            yield event.plain_result("请输入有效的倒数日ID")
    
    @filter.command("countdownhelp")
    async def help_command(self, event: AstrMessageEvent):
        '''倒数日帮助'''
        help_text = """
倒数日插件使用说明:
/addcountdown <名称> <日期YYYY-MM-DD> - 添加倒数日
/listcountdown - 显示所有倒数日
/deletecountdown <ID> - 删除指定倒数日
/countdownhelp - 显示帮助信息

示例:
/addcountdown 生日 2025-12-31
/listcountdown
/deletecountdown 1
        """
        yield event.plain_result(help_text)
    
    async def terminate(self):
        '''插件卸载时调用'''
        logger.info("倒数日插件已卸载")