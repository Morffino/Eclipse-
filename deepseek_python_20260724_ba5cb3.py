import discord
from discord.ext import commands
from datetime import datetime, timedelta
import asyncio
from typing import Dict
from models.ticket import Ticket
from utils.database import Database
from utils.logger import Logger
from config import Config

class TicketView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.tickets: Dict[int, Ticket] = {}
        self.db = Database()
        self.logger = Logger(bot, Config.LOG_CHANNEL_ID)
    
    @discord.ui.button(label="Общие вопросы", style=discord.ButtonStyle.primary, custom_id="general")
    async def general_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Общие вопросы")
    
    @discord.ui.button(label="Восстановление вещей", style=discord.ButtonStyle.success, custom_id="restore")
    async def restore_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Восстановление вещей")
    
    @discord.ui.button(label="Технические проблемы", style=discord.ButtonStyle.warning, custom_id="tech")
    async def tech_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Технические проблемы")
    
    @discord.ui.button(label="Жалоба на игрока", style=discord.ButtonStyle.danger, custom_id="player_report")
    async def player_report_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Жалоба на игрока/группировку")
    
    @discord.ui.button(label="Жалоба на Администрацию", style=discord.ButtonStyle.danger, custom_id="admin_report")
    async def admin_report_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Жалоба на Администрацию")
    
    async def create_ticket(self, interaction: discord.Interaction, topic: str):
        # Проверка на существующий тикет
        for ticket in self.tickets.values():
            if ticket.user_id == interaction.user.id and ticket.status == 'open':
                await interaction.response.send_message("У вас уже есть открытый тикет!", ephemeral=True)
                return
        
        # Создание канала
        guild = interaction.guild
        category = discord.utils.get(guild.categories, id=Config.CATEGORY_ID)
        
        if not category:
            await interaction.response.send_message("Категория для тикетов не найдена!", ephemeral=True)
            return
        
        # Создаем имя канала
        ticket_number = len([t for t in self.tickets.values() if t.status == 'open']) + 1
        channel_name = f"ticket-{interaction.user.name.lower()}-{ticket_number}"
        
        # Права доступа
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.get_role(Config.STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }
        
        # Создаем канал
        channel = await guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"Тикет от {interaction.user.name} - {topic}"
        )
        
        # Создаем тикет
        ticket = Ticket(channel.id, interaction.user.id, interaction.user.name, topic)
        ticket.closing_time = datetime.now() + timedelta(hours=Config.TICKET_LIFETIME_HOURS)
        self.tickets[channel.id] = ticket
        
        # Сохраняем в базу данных
        self.db.add_ticket(ticket)
        
        # Отправляем сообщение в канал
        embed = discord.Embed(
            title="HS TICKET | Центр поддержки",
            description=f"Тикет создан по теме: **{topic}**",
            color=Config.COLORS['success']
        )
        embed.add_field(name="Укажите ваш SteamID64", value="Можно узнать тут: https://steamid.io", inline=False)
        embed.add_field(name="Ваш ник в игре", value="Укажите игровой ник", inline=False)
        embed.add_field(name="Кратко о проблеме", value="До 30 символов", inline=False)
        embed.add_field(
            name="⏰ Время до автоматического закрытия",
            value=f"Тикет будет автоматически закрыт через {Config.TICKET_LIFETIME_HOURS} часов",
            inline=False
        )
        embed.set_footer(text=f"Тикет создан: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        
        view = TicketControlView(self.bot, self.tickets, self.db, self.logger)
        await channel.send(f"{interaction.user.mention} {guild.get_role(Config.STAFF_ROLE_ID).mention}", embed=embed, view=view)
        
        # Запускаем таймер автоматического закрытия
        self.bot.loop.create_task(self.auto_close_ticket(channel.id))
        
        # Логирование
        await self.logger.log_ticket_created(interaction.user, topic, channel)
        
        await interaction.response.send_message(f"Тикет создан! Перейдите в канал {channel.mention}", ephemeral=True)
    
    async def auto_close_ticket(self, channel_id: int):
        """Автоматическое закрытие тикета"""
        await asyncio.sleep(Config.TICKET_LIFETIME_HOURS * 3600)
        
        if channel_id not in self.tickets:
            return
        
        ticket = self.tickets[channel_id]
        if ticket.status != 'open':
            return
        
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return
        
        # Уведомляем о закрытии
        embed = discord.Embed(
            title="⏰ Автоматическое закрытие",
            description=f"Тикет будет закрыт через 60 секунд, так как истекло время ({Config.TICKET_LIFETIME_HOURS} часов).",
            color=Config.COLORS['error']
        )
        await channel.send(embed=embed)
        
        await asyncio.sleep(60)
        
        if channel_id not in self.tickets:
            return
        
        if self.tickets[channel_id].status != 'open':
            return
        
        await self.close_ticket(channel, self.bot.user, "Автоматическое закрытие по истечении времени")
    
    async def close_ticket(self, channel, closer, reason="Закрыт"):
        """Закрытие тикета"""
        if channel.id not in self.tickets:
            return
        
        ticket = self.tickets[channel.id]
        ticket.status = 'closed'
        
        # Собираем сообщения
        messages = []
        async for msg in channel.history(limit=500, oldest_first=True):
            messages.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author.name} ({msg.author.id}): {msg.content}")
        
        # Получаем персонал
        staff_list = []
        async for msg in channel.history(limit=200):
            if msg.author.guild_permissions.administrator or msg.author.get_role(Config.STAFF_ROLE_ID):
                if msg.author.id not in staff_list:
                    staff_list.append(msg.author.id)
        
        # Сохраняем в базу данных
        self.db.close_ticket(
            channel.id,
            closer.name if hasattr(closer, 'name') else 'Auto',
            reason,
            messages,
            staff_list
        )
        
        # Логируем
        await self.logger.log_ticket_closed(
            self.db.get_ticket(channel.id),
            closer,
            reason,
            messages,
            staff_list,
            channel.id
        )
        
        # Удаляем тикет
        del self.tickets[channel.id]
        
        # Удаляем канал
        await channel.delete()

class TicketControlView(discord.ui.View):
    def __init__(self, bot, tickets, db, logger):
        super().__init__(timeout=None)
        self.bot = bot
        self.tickets = tickets
        self.db = db
        self.logger = logger
    
    @discord.ui.button(label="Закрыть тикет", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator and not interaction.user.get_role(Config.STAFF_ROLE_ID):
            await interaction.response.send_message("У вас нет прав для закрытия тикета!", ephemeral=True)
            return
        
        channel = interaction.channel
        if channel.id not in self.tickets:
            await interaction.response.send_message("Этот тикет не найден в системе!", ephemeral=True)
            return
        
        await self.tickets[channel.id].close_ticket(channel, interaction.user, "Закрыт по запросу персонала")
        await interaction.response.send_message("Тикет будет закрыт через 5 секунд...")
    
    @discord.ui.button(label="Продлить тикет", style=discord.ButtonStyle.primary, custom_id="extend_ticket")
    async def extend_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator and not interaction.user.get_role(Config.STAFF_ROLE_ID):
            await interaction.response.send_message("У вас нет прав для продления тикета!", ephemeral=True)
            return
        
        channel = interaction.channel
        if channel.id not in self.tickets:
            await interaction.response.send_message("Этот тикет не найден в системе!", ephemeral=True)
            return
        
        ticket = self.tickets[channel.id]
        ticket.closing_time = datetime.now() + timedelta(hours=Config.TICKET_LIFETIME_HOURS)
        ticket.extended = True
        
        embed = discord.Embed(
            title="⏰ Тикет продлен",
            description=f"Тикет продлен на {Config.TICKET_LIFETIME_HOURS} часов.\nНовое время закрытия: {ticket.closing_time.strftime('%d.%m.%Y %H:%M')}",
            color=Config.COLORS['success']
        )
        await channel.send(embed=embed)
        
        await interaction.response.send_message("Тикет успешно продлен!", ephemeral=True)
    
    @discord.ui.button(label="Сохранить лог", style=discord.ButtonStyle.secondary, custom_id="save_log")
    async def save_log_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator and not interaction.user.get_role(Config.STAFF_ROLE_ID):
            await interaction.response.send_message("У вас нет прав для сохранения лога!", ephemeral=True)
            return
        
        channel = interaction.channel
        if channel.id not in self.tickets:
            await interaction.response.send_message("Этот тикет не найден в системе!", ephemeral=True)
            return
        
        # Создаем лог
        messages = []
        async for msg in channel.history(limit=200, oldest_first=True):
            messages.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author.name}: {msg.content}")
        
        log_text = f"""=== ЛОГ ТИКЕТА ===
ID тикета: {channel.id}
Создан: {self.tickets[channel.id].created_at.strftime('%Y-%m-%d %H:%M:%S')}
Пользователь: {self.tickets[channel.id].user_name} ({self.tickets[channel.id].user_id})
Тема: {self.tickets[channel.id].topic}
========================

"""
        log_text += "\n".join(messages)
        
        filename = f"data/logs/ticket_log_{channel.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        os.makedirs('data/logs', exist_ok=True)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(log_text)
        
        await interaction.response.send_message("Лог сохранен:", file=discord.File(filename))
        os.remove(filename)

class TicketsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.logger = Logger(bot, Config.LOG_CHANNEL_ID)
        self.tickets = {}
    
    @commands.command(name='setup')
    @commands.has_permissions(administrator=True)
    async def setup_tickets(self, ctx):
        """Настройка системы тикетов"""
        embed = discord.Embed(
            title="Добро пожаловать",
            description="Это начало канала #кикеты.",
            color=Config.COLORS['info']
        )
        embed.add_field(
            name="HS HELPER [БОТ]",
            value=f"**HS TICKET | Центр поддержки**\nНужна помощь, восстановление. Выбери подходящую тему кнопки обращения.\n\n**Важно:** создавайте текст только увидите нужная команда.\n\n⏰ **Тикеты автоматически закрываются через {Config.TICKET_LIFETIME_HOURS} часов**",
            inline=False
        )
        
        view = TicketView(self.bot)
        await ctx.send(embed=embed, view=view)
        await ctx.message.delete()
        await ctx.send("Система тикетов настроена!", ephemeral=True)
    
    @commands.command(name='stats')
    @commands.has_permissions(administrator=True)
    async def ticket_stats(self, ctx):
        """Показать статистику по тикетам"""
        stats = self.db.get_stats()
        
        embed = discord.Embed(
            title="📊 Статистика тикетов",
            color=Config.COLORS['info'],
            timestamp=datetime.now()
        )
        embed.add_field(name="🟢 Открытых тикетов", value=stats['open'], inline=True)
        embed.add_field(name="🔴 Закрытых тикетов", value=stats['closed'], inline=True)
        embed.add_field(name="📋 Всего тикетов", value=stats['total'], inline=True)
        
        if stats['topics']:
            topic_stats = ""
            for topic, count in sorted(stats['topics'].items(), key=lambda x: x[1], reverse=True):
                topic_stats += f"- {topic}: {count}\n"
            embed.add_field(name="📈 Статистика по типам", value=topic_stats, inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='logs')
    @commands.has_permissions(administrator=True)
    async def view_logs(self, ctx, ticket_id: int = None):
        """Просмотр логов тикетов"""
        if ticket_id is None:
            recent_tickets = list(self.db.history.items())[-5:]
            embed = discord.Embed(
                title="📋 Последние закрытые тикеты",
                color=Config.COLORS['info']
            )
            for tid, info in recent_tickets:
                embed.add_field(
                    name=f"Тикет #{tid}",
                    value=f"👤 {info['user_name']}\n📂 {info['topic']}\n🔒 {info['closed_by'] if info['closed_by'] else 'Auto'}\n📅 {info['closed_at'][:16] if info['closed_at'] else 'Не закрыт'}",
                    inline=False
                )
            await ctx.send(embed=embed)
        else:
            info = self.db.get_ticket(ticket_id)
            if info:
                embed = discord.Embed(
                    title=f"📋 Детали тикета #{ticket_id}",
                    color=Config.COLORS['info']
                )
                embed.add_field(name="👤 Пользователь", value=f"{info['user_name']} (ID: {info['user_id']})", inline=False)
                embed.add_field(name="📂 Тема", value=info['topic'], inline=True)
                embed.add_field(name="📅 Создан", value=info['created_at'][:16], inline=True)
                embed.add_field(name="🔒 Закрыт", value=info['closed_at'][:16] if info['closed_at'] else "Открыт", inline=True)
                
                if info['staff_members']:
                    staff_names = []
                    for staff_id in info['staff_members']:
                        staff = self.bot.get_user(staff_id)
                        if staff:
                            staff_names.append(staff.name)
                    if staff_names:
                        embed.add_field(name="👥 Персонал", value=", ".join(staff_names), inline=False)
                
                await ctx.send(embed=embed)
            else:
                await ctx.send("Тикет с таким ID не найден в истории!")

async def setup(bot):
    await bot.add_cog(TicketsCog(bot))