import discord
from discord.ext import commands
import json
import os
from datetime import datetime, timedelta
import asyncio

# Конфигурация
TOKEN = 'YOUR_BOT_TOKEN_HERE'
GUILD_ID = 123456789012345678  # ID вашего сервера
CATEGORY_ID = 123456789012345678  # ID категории для тикетов
STAFF_ROLE_ID = 123456789012345678  # ID роли персонала
LOG_CHANNEL_ID = 123456789012345678  # ID канала для логов
TICKET_LIFETIME_HOURS = 10  # Время жизни тикета в часах

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Хранилище активных тикетов
tickets = {}

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
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
        for ticket in tickets.values():
            if ticket['user_id'] == interaction.user.id and ticket['status'] == 'open':
                await interaction.response.send_message("У вас уже есть открытый тикет!", ephemeral=True)
                return
        
        # Создание канала
        guild = interaction.guild
        category = discord.utils.get(guild.categories, id=CATEGORY_ID)
        
        # Создаем имя канала
        ticket_number = len([t for t in tickets.values() if t['status'] == 'open']) + 1
        channel_name = f"ticket-{interaction.user.name.lower()}-{ticket_number}"
        
        # Права доступа
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }
        
        # Создаем канал
        channel = await guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"Тикет от {interaction.user.name} - {topic}"
        )
        
        # Сохраняем информацию о тикете
        tickets[channel.id] = {
            'user_id': interaction.user.id,
            'topic': topic,
            'status': 'open',
            'created_at': datetime.now(),
            'closing_time': datetime.now() + timedelta(hours=TICKET_LIFETIME_HOURS)
        }
        
        # Отправляем сообщение в канал
        embed = discord.Embed(
            title=f"HS TICKET | Центр поддержки",
            description=f"Тикет создан по теме: **{topic}**",
            color=0x00ff00
        )
        embed.add_field(name="Укажите ваш SteamID64", value="Можно узнать тут: https://steamid.io", inline=False)
        embed.add_field(name="Ваш ник в игре", value="Укажите игровой ник", inline=False)
        embed.add_field(name="Кратко о проблеме", value="До 30 символов", inline=False)
        embed.add_field(
            name="⏰ Время до автоматического закрытия", 
            value=f"Тикет будет автоматически закрыт через {TICKET_LIFETIME_HOURS} часов", 
            inline=False
        )
        embed.set_footer(text=f"Тикет создан: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        
        await channel.send(f"{interaction.user.mention} {guild.get_role(STAFF_ROLE_ID).mention}", embed=embed)
        
        # Добавляем кнопки управления тикетом
        view = TicketControlView()
        await channel.send("**Управление тикетом:**", view=view)
        
        # Запускаем таймер автоматического закрытия
        bot.loop.create_task(auto_close_ticket(channel.id))
        
        # Логирование
        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title="📩 Создан новый тикет",
                description=f"Пользователь: {interaction.user.mention}\nТема: {topic}\nКанал: {channel.mention}\nАвтоматическое закрытие через: {TICKET_LIFETIME_HOURS} часов",
                color=0x00ff00
            )
            await log_channel.send(embed=log_embed)
        
        await interaction.response.send_message(f"Тикет создан! Перейдите в канал {channel.mention}", ephemeral=True)

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Закрыть тикет", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Проверка прав
        if not interaction.user.guild_permissions.administrator and not interaction.user.get_role(STAFF_ROLE_ID):
            await interaction.response.send_message("У вас нет прав для закрытия тикета!", ephemeral=True)
            return
        
        channel = interaction.channel
        if channel.id not in tickets:
            await interaction.response.send_message("Этот тикет не найден в системе!", ephemeral=True)
            return
        
        # Закрываем тикет
        await close_ticket(channel, interaction.user)
        
        await interaction.response.send_message("Тикет будет закрыт через 5 секунд...")
    
    @discord.ui.button(label="Продлить тикет", style=discord.ButtonStyle.primary, custom_id="extend_ticket")
    async def extend_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Проверка прав
        if not interaction.user.guild_permissions.administrator and not interaction.user.get_role(STAFF_ROLE_ID):
            await interaction.response.send_message("У вас нет прав для продления тикета!", ephemeral=True)
            return
        
        channel = interaction.channel
        if channel.id not in tickets:
            await interaction.response.send_message("Этот тикет не найден в системе!", ephemeral=True)
            return
        
        # Продлеваем тикет на 10 часов
        tickets[channel.id]['closing_time'] = datetime.now() + timedelta(hours=TICKET_LIFETIME_HOURS)
        tickets[channel.id]['extended'] = True
        
        # Отправляем сообщение
        embed = discord.Embed(
            title="⏰ Тикет продлен",
            description=f"Тикет продлен на {TICKET_LIFETIME_HOURS} часов. Новое время закрытия: {tickets[channel.id]['closing_time'].strftime('%d.%m.%Y %H:%M')}",
            color=0x00ff00
        )
        await channel.send(embed=embed)
        
        await interaction.response.send_message("Тикет успешно продлен!", ephemeral=True)

async def auto_close_ticket(channel_id):
    """Автоматическое закрытие тикета по истечении времени"""
    await asyncio.sleep(TICKET_LIFETIME_HOURS * 3600)  # Ждем указанное количество часов
    
    # Проверяем, существует ли еще тикет
    if channel_id not in tickets:
        return
    
    if tickets[channel_id]['status'] != 'open':
        return
    
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    
    # Уведомляем о закрытии
    embed = discord.Embed(
        title="⏰ Автоматическое закрытие",
        description=f"Тикет будет закрыт через 60 секунд, так как истекло время ({TICKET_LIFETIME_HOURS} часов).",
        color=0xff0000
    )
    await channel.send(embed=embed)
    
    await asyncio.sleep(60)  # Даем время на реакцию
    
    # Проверяем еще раз
    if channel_id not in tickets:
        return
    
    if tickets[channel_id]['status'] != 'open':
        return
    
    # Закрываем тикет
    await close_ticket(channel, bot.user)

async def close_ticket(channel, closer):
    """Закрытие тикета"""
    if channel.id not in tickets:
        return
    
    # Логирование
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        ticket_info = tickets[channel.id]
        log_embed = discord.Embed(
            title="📪 Тикет закрыт",
            description=f"Закрыл: {closer.mention if hasattr(closer, 'mention') else 'Автоматически'}\nКанал: {channel.mention}\nПользователь: <@{ticket_info['user_id']}>\nТема: {ticket_info['topic']}\nВремя жизни: {(datetime.now() - ticket_info['created_at']).total_seconds() / 3600:.1f} часов",
            color=0xff0000
        )
        await log_channel.send(embed=log_embed)
    
    # Удаляем тикет из словаря
    del tickets[channel.id]
    
    # Удаляем канал
    await channel.delete()

@bot.event
async def on_ready():
    print(f'Бот {bot.user} успешно запущен!')
    
    # Проверка истекающих тикетов при запуске
    for channel_id, ticket_info in list(tickets.items()):
        if ticket_info['status'] == 'open' and datetime.now() >= ticket_info['closing_time']:
            channel = bot.get_channel(channel_id)
            if channel:
                await close_ticket(channel, bot.user)
    
    # Создание основного сообщения с тикетами
    guild = bot.get_guild(GUILD_ID)
    if guild:
        # Ищем канал для тикетов (можно заменить на конкретный ID)
        ticket_channel = discord.utils.get(guild.text_channels, name="tickets")
        if ticket_channel:
            # Очищаем старые сообщения
            async for message in ticket_channel.history(limit=100):
                if message.author == bot.user:
                    await message.delete()
            
            # Создаем новое сообщение
            embed = discord.Embed(
                title="Добро пожаловать",
                description="Это начало канала #кикеты.",
                color=0x3498db
            )
            embed.add_field(
                name="HS HELPER [БОТ]",
                value=f"02.07.2026 13:31\n\n**HS TICKET | Центр поддержки**\nНужна помощь, восстановление. Выбери подходящую тему кнопки обращения.\n\n**Важно:** создавайте текст только увидите нужная команда.\n\n⏰ **Тикеты автоматически закрываются через {TICKET_LIFETIME_HOURS} часов**",
                inline=False
            )
            
            view = TicketView()
            await ticket_channel.send(embed=embed, view=view)
            print("Сообщение с тикетами создано!")

@bot.command(name='setup_tickets')
@commands.has_permissions(administrator=True)
async def setup_tickets(ctx):
    """Команда для настройки системы тикетов"""
    embed = discord.Embed(
        title="Добро пожаловать",
        description="Это начало канала #кикеты.",
        color=0x3498db
    )
    embed.add_field(
        name="HS HELPER [БОТ]",
        value=f"02.07.2026 13:31\n\n**HS TICKET | Центр поддержки**\nНужна помощь, восстановление. Выбери подходящую тему кнопки обращения.\n\n**Важно:** создавайте текст только увидите нужная команда.\n\n⏰ **Тикеты автоматически закрываются через {TICKET_LIFETIME_HOURS} часов**",
        inline=False
    )
    
    view = TicketView()
    await ctx.send(embed=embed, view=view)
    await ctx.message.delete()

@bot.command(name='set_ticket_lifetime')
@commands.has_permissions(administrator=True)
async def set_ticket_lifetime(ctx, hours: int):
    """Установить время жизни тикета в часах"""
    global TICKET_LIFETIME_HOURS
    TICKET_LIFETIME_HOURS = hours
    await ctx.send(f"Время жизни тикетов установлено на {hours} часов!")

@bot.command(name='ticket_stats')
@commands.has_permissions(administrator=True)
async def ticket_stats(ctx):
    """Показать статистику по тикетам"""
    open_tickets = [t for t in tickets.values() if t['status'] == 'open']
    closed_tickets = [t for t in tickets.values() if t['status'] == 'closed']
    
    embed = discord.Embed(
        title="📊 Статистика тикетов",
        color=0x3498db
    )
    embed.add_field(name="Открытых тикетов", value=len(open_tickets), inline=True)
    embed.add_field(name="Закрытых тикетов", value=len(closed_tickets), inline=True)
    embed.add_field(name="Всего тикетов", value=len(tickets), inline=True)
    
    if open_tickets:
        ticket_list = ""
        for ticket_id, ticket_info in list(tickets.items())[:10]:
            if ticket_info['status'] == 'open':
                channel = bot.get_channel(ticket_id)
                if channel:
                    time_left = (ticket_info['closing_time'] - datetime.now())
                    hours_left = time_left.total_seconds() / 3600
                    ticket_list += f"- {channel.mention} ({ticket_info['topic']}) - осталось {hours_left:.1f} ч\n"
        if ticket_list:
            embed.add_field(name="Активные тикеты", value=ticket_list, inline=False)
    
    await ctx.send(embed=embed)

# Запуск бота
bot.run(TOKEN)