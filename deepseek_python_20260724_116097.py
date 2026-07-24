import discord
from datetime import datetime
from typing import Optional
import aiofiles
import os

class Logger:
    def __init__(self, bot, log_channel_id: int):
        self.bot = bot
        self.log_channel_id = log_channel_id
    
    async def log(self, embed: discord.Embed, file: Optional[discord.File] = None):
        """Отправка лога в канал"""
        channel = self.bot.get_channel(self.log_channel_id)
        if channel:
            try:
                if file:
                    await channel.send(embed=embed, file=file)
                else:
                    await channel.send(embed=embed)
            except Exception as e:
                print(f"Ошибка отправки лога: {e}")
    
    async def log_ticket_created(self, user: discord.User, topic: str, channel: discord.TextChannel):
        """Лог создания тикета"""
        embed = discord.Embed(
            title="📩 Создан новый тикет",
            description=f"**Пользователь:** {user.mention} ({user.name})\n**Тема:** {topic}\n**Канал:** {channel.mention}",
            color=0x00ff00,
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"ID тикета: {channel.id}")
        await self.log(embed)
    
    async def log_ticket_closed(self, ticket_info: dict, closer, reason: str, 
                                messages: list, staff_list: list, channel_id: int):
        """Лог закрытия тикета"""
        # Основной лог
        embed = discord.Embed(
            title="📪 Тикет закрыт",
            description=f"**Информация о тикете:**",
            color=0xff0000,
            timestamp=datetime.now()
        )
        
        user = self.bot.get_user(ticket_info['user_id'])
        user_mention = user.mention if user else f"<@{ticket_info['user_id']}>"
        
        embed.add_field(
            name="👤 Создатель",
            value=f"{user_mention}\n{ticket_info['user_name']} (ID: {ticket_info['user_id']})",
            inline=False
        )
        
        embed.add_field(
            name="📂 Тема",
            value=ticket_info['topic'],
            inline=True
        )
        
        created_at = datetime.fromisoformat(ticket_info['created_at']) if isinstance(ticket_info['created_at'], str) else ticket_info['created_at']
        time_lived = (datetime.now() - created_at).total_seconds() / 3600
        
        embed.add_field(
            name="⏱ Время жизни",
            value=f"{time_lived:.1f} часов",
            inline=True
        )
        
        embed.add_field(
            name="🔒 Закрыл",
            value=f"{closer.mention if hasattr(closer, 'mention') else '🤖 Автоматически'}",
            inline=True
        )
        
        embed.add_field(
            name="📝 Причина",
            value=reason,
            inline=False
        )
        
        if staff_list:
            staff_mentions = []
            for staff_id in staff_list:
                staff_member = self.bot.get_user(staff_id)
                if staff_member:
                    staff_mentions.append(staff_member.mention)
            if staff_mentions:
                embed.add_field(
                    name="👥 Участвовавший персонал",
                    value=", ".join(staff_mentions),
                    inline=False
                )
        
        embed.add_field(
            name="📊 Всего сообщений",
            value=f"{len(messages)} сообщений",
            inline=True
        )
        
        embed.set_footer(text=f"ID тикета: {channel_id}")
        
        # Создаем файл с полным логом
        log_text = self.create_log_file(ticket_info, messages, closer, reason, channel_id)
        
        # Сохраняем файл
        filename = f"data/logs/ticket_log_{channel_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        os.makedirs('data/logs', exist_ok=True)
        
        async with aiofiles.open(filename, 'w', encoding='utf-8') as f:
            await f.write(log_text)
        
        file = discord.File(filename)
        
        await self.log(embed, file)
        
        # Удаляем файл после отправки
        os.remove(filename)
    
    def create_log_file(self, ticket_info: dict, messages: list, closer, reason: str, channel_id: int) -> str:
        """Создание текстового файла лога"""
        log_text = f"""=== ПОЛНЫЙ ЛОГ ТИКЕТА ===
ID тикета: {channel_id}
Создан: {ticket_info['created_at']}
Закрыт: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Пользователь: {ticket_info['user_name']} (ID: {ticket_info['user_id']})
Тема: {ticket_info['topic']}
Закрыл: {closer.name if hasattr(closer, 'name') else 'Auto'}
Причина: {reason}
========================

=== ИСТОРИЯ СООБЩЕНИЙ ===
"""
        log_text += "\n".join(messages)
        return log_text