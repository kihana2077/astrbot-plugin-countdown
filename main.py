import sqlite3
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from astrbot.core.plugin import PluginBase
from astrbot.core.message import AstrMessageEvent

class CountdownPlugin(PluginBase):
    def __init__(self, bot):
        super().__init__(bot)
        self.db_path = os.path.join(self.bot.data_dir, "countdown.db")
        self.init_db()
        
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
                    remark TEXT,
                    user_id TEXT,
                    chat_id TEXT
                )
            """)
            conn.commit()
    
    async def add_countdown(self, name: str, target_date: str, remark: str = "", 
                          user_id: str = "", chat_id: str = "") -> bool:
        """添加倒数日"""
        try:
            # 验证日期格式
            datetime.strptime(target_date, "%Y-%m-%d")
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO countdowns (name, target_date, created_date, remark, user_id, chat_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (name, target_date, datetime.now().strftime("%Y-%m-%d"), remark, user_id, chat_id)
                )
                conn.commit()
            return True
        except ValueError:
            return False
        except Exception as e:
            self.logger.error(f"添加倒数日失败: {e}")
            return False
    
    async def delete_countdown(self, countdown_id: int) -> bool:
        """删除倒数日"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM countdowns WHERE id = ?", (countdown_id,))
                conn.commit()
            return True
        except Exception as e:
            self.logger.error(f"删除倒数日失败: {e}")
            return False
    
    async def list_countdowns(self, user_id: str = "", chat_id: str = "") -> List[Dict[str, Any]]:
        """获取倒数日列表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                if user_id:
                    cursor.execute(
                        "SELECT * FROM countdowns WHERE user_id = ? ORDER BY target_date",
                        (user_id,)
                    )
                elif chat_id:
                    cursor.execute(
                        "SELECT * FROM countdowns WHERE chat_id = ? ORDER BY target_date",
                        (chat_id,)
                    )
                else:
                    cursor.execute("SELECT * FROM countdowns ORDER BY target_date")
                
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
                        'days_left': days_diff,
                        'remark': row['remark']
                    })
                
                return result
        except Exception as e:
            self.logger.error(f"获取倒数日列表失败: {e}")
            return []
    
    async def handle_command(self, event: AstrMessageEvent):
        """处理命令"""
        text = event.message.text.strip()
        args = text.split()
        
        if len(args) < 1:
            return False
        
        # 添加倒数日命令: /countdown add 生日 2025-12-31
        if args[0] == "/countdown" and len(args) >= 4 and args[1] == "add":
            name = args[2]
            date_str = args[3]
            remark = " ".join(args[4:]) if len(args) > 4 else ""
            
            success = await self.add_countdown(
                name, date_str, remark, 
                event.message.sender.user_id, 
                event.message.chat.chat_id
            )
            
            if success:
                await event.reply(f"已添加倒数日: {name} - {date_str}")
            else:
                await event.reply("添加失败，请检查日期格式(YYYY-MM-DD)")
            return True
        
        # 列出倒数日命令: /countdown list
        elif args[0] == "/countdown" and len(args) >= 2 and args[1] == "list":
            countdowns = await self.list_countdowns(
                event.message.sender.user_id,
                event.message.chat.chat_id
            )
            
            if not countdowns:
                await event.reply("暂无倒数日记录")
                return True
            
            response = "倒数日列表:\n"
            for cd in countdowns:
                status = "已过期" if cd['days_left'] < 0 else f"剩余{cd['days_left']}天"
                response += f"{cd['id']}. {cd['name']} - {cd['target_date']} ({status})\n"
                if cd['remark']:
                    response += f"   备注: {cd['remark']}\n"
            
            await event.reply(response)
            return True
        
        # 删除倒数日命令: /countdown delete 1
        elif args[0] == "/countdown" and len(args) >= 3 and args[1] == "delete":
            try:
                cd_id = int(args[2])
                success = await self.delete_countdown(cd_id)
                
                if success:
                    await event.reply(f"已删除倒数日 #{cd_id}")
                else:
                    await event.reply("删除失败，请检查ID是否正确")
            except ValueError:
                await event.reply("请输入有效的倒数日ID")
            return True
        
        # 帮助命令: /countdown help
        elif args[0] == "/countdown" and len(args) >= 2 and args[1] == "help":
            help_text = """
倒数日插件使用说明:
/addcountdown <名称> <日期YYYY-MM-DD> [备注] - 添加倒数日
/countdown list - 显示所有倒数日
/countdown delete <ID> - 删除指定倒数日
/countdown help - 显示帮助信息

示例:
/addcountdown 生日 2025-12-31 我的生日
/countdown list
/countdown delete 1
            """
            await event.reply(help_text)
            return True
        
        return False
    
    async def handle_natural_language(self, event: AstrMessageEvent):
        """处理自然语言"""
        text = event.message.text.strip().lower()
        
        # 自然语言添加倒数日
        if "添加倒数日" in text or "设置倒数日" in text:
            # 这里可以添加更复杂的自然语言解析逻辑
            # 简化版：提取日期和事件名称
            await event.reply("请使用命令格式: /addcountdown <名称> <日期YYYY-MM-DD> [备注]")
            return True
        
        return False
    
    async def on_message(self, event: AstrMessageEvent):
        """处理消息事件"""
        # 优先处理命令
        if await self.handle_command(event):
            return
        
        # 处理自然语言
        if await self.handle_natural_language(event):
            return

# 插件注册
def setup(bot):
    bot.register_plugin(CountdownPlugin(bot))