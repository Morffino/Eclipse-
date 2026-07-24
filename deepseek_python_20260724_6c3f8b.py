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
# Хранилище истории тикетов
ticket_history = {}

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
            'user_name': interaction.user.name,
            'user_display': interaction.user.display_name,
            'topic': topic,
            'status': 'open',
            'created_at': datetime.now(),
            'closing_time': datetime.now() + timedelta(hours=TICKET_LIFETIME_HOURS),
            'messages': [],
            'staff_members': []
        }
        
        # Сохраняем в историю
        ticket_history[channel.id] = {
            'user_id': interaction.user.id,
            'user_name': interaction.user.name,
            'topic': topic,
            'created_at': datetime.now(),
            'closed_at': None,
            'closed_by': None,
            'close_reason': None,
            'messages': [],
            'staff_members': []
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
        
        # Логирование создания
        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title="📩 Создан новый тикет",
                description=f"**Пользователь:** {interaction.user.mention} ({interaction.user.name})\n**Тема:** {topic}\n**Канал:** {channel.mention}\n**Автоматическое закрытие через:** {TICKET_LIFETIME_HOURS} часов",
                color=0x00ff00,
                timestamp=datetime.now()
            )
            log_embed.set_footer(text=f"ID тикета: {channel.id}")
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
        await close_ticket(channel, interaction.user, "Закрыт по запросу персонала")
        
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
        
        # Логирование продления
        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title="⏰ Тикет продлен",
                description=f"**Персонал:** {interaction.user.mention}\n**Канал:** {channel.mention}\n**Новое время закрытия:** {tickets[channel.id]['closing_time'].strftime('%d.%m.%Y %H:%M')}",
                color=0x3498db,
                timestamp=datetime.now()
            )
            await log_channel.send(embed=log_embed)
        
        # Отправляем сообщение
        embed = discord.Embed(
            title="⏰ Тикет продлен",
            description=f"Тикет продлен на {TICKET_LIFETIME_HOURS} часов.\nНовое время закрытия: {tickets[channel.id]['closing_time'].strftime('%d.%m.%Y %H:%M')}",
            color=0x00ff00
        )
        await channel.send(embed=embed)
        
        await interaction.response.send_message("Тикет успешно продлен!", ephemeral=True)
    
    @discord.ui.button(label="Сохранить лог", style=discord.ButtonStyle.secondary, custom_id="save_log")
    async def save_log(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Проверка прав
        if not interaction.user.guild_permissions.administrator and not interaction.user.get_role(STAFF_ROLE_ID):
            await interaction.response.send_message("У вас нет прав для сохранения лога!", ephemeral=True)
            return
        
        channel = interaction.channel
        if channel.id not in tickets:
            await interaction.response.send_message("Этот тикет не найден в системе!", ephemeral=True)
            return
        
        # Собираем историю сообщений
        messages = []
        async for msg in channel.history(limit=200, oldest_first=True):
            messages.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author.name}: {msg.content}")
        
        # Создаем файл лога
        log_text = f"""=== ЛОГ ТИКЕТА ===
ID тикета: {channel.id}
Создан: {tickets[channel.id]['created_at'].strftime('%Y-%m-%d %H:%M:%S')}
Пользователь: {tickets[channel.id]['user_name']} ({tickets[channel.id]['user_id']})
Тема: {tickets[channel.id]['topic']}
========================

"""
        log_text += "\n".join(messages)
        
        # Сохраняем в файл
        filename = f"ticket_log_{channel.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(log_text)
        
        # Отправляем файл
        await interaction.response.send_message("Лог сохранен:", file=discord.File(filename))
        
        # Удаляем временный файл
        os.remove(filename)

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
    await close_ticket(channel, bot.user, "Автоматическое закрытие по истечении времени")

async def close_ticket(channel, closer, reason="Закрыт"):
    """Закрытие тикета с полным логированием"""
    if channel.id not in tickets:
        return
    
    ticket_info = tickets[channel.id]
    
    # Собираем последние сообщения для лога
    messages = []
    async for msg in channel.history(limit=50, oldest_first=True):
        messages.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author.name}: {msg.content[:100]}")
    
    # Получаем информацию о персонале
    staff_list = []
    async for msg in channel.history(limit=200):
        if msg.author.guild_permissions.administrator or msg.author.get_role(STAFF_ROLE_ID):
            if msg.author.id not in staff_list:
                staff_list.append(msg.author.id)
    
    # Обновляем историю
    if channel.id in ticket_history:
        ticket_history[channel.id]['closed_at'] = datetime.now()
        ticket_history[channel.id]['closed_by'] = closer.id if closer != bot.user else "Auto"
        ticket_history[channel.id]['close_reason'] = reason
        ticket_history[channel.id]['staff_members'] = staff_list
        ticket_history[channel.id]['messages'] = messages
    
    # Логирование в канал логов
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        # Основной лог закрытия
        close_embed = discord.Embed(
            title="📪 Тикет закрыт",
            description=f"**Информация о тикете:**",
            color=0xff0000,
            timestamp=datetime.now()
        )
        
        # Информация о создателе
        user = bot.get_user(ticket_info['user_id'])
        user_mention = user.mention if user else f"<@{ticket_info['user_id']}>"
        
        close_embed.add_field(
            name="👤 Создатель",
            value=f"{user_mention}\n{ticket_info['user_name']} (ID: {ticket_info['user_id']})",
            inline=False
        )
        
        close_embed.add_field(
            name="📂 Тема",
            value=ticket_info['topic'],
            inline=True
        )
        
        close_embed.add_field(
            name="⏱ Время жизни",
            value=f"{(datetime.now() - ticket_info['created_at']).total_seconds() / 3600:.1f} часов",
            inline=True
        )
        
        close_embed.add_field(
            name="🔒 Закрыл",
            value=f"{closer.mention if hasattr(closer, 'mention') else '🤖 Автоматически'}",
            inline=True
        )
        
        close_embed.add_field(
            name="📝 Причина",
            value=reason,
            inline=False
        )
        
        if staff_list:
            staff_mentions = []
            for staff_id in staff_list:
                staff_member = bot.get_user(staff_id)
                if staff_member:
                    staff_mentions.append(staff_member.mention)
            if staff_mentions:
                close_embed.add_field(
                    name="👥 Участвовавший персонал",
                    value=", ".join(staff_mentions),
                    inline=False
                )
        
        close_embed.add_field(
            name="📊 Всего сообщений",
            value=f"{len(messages)} сообщений",
            inline=True
        )
        
        close_embed.set_footer(text=f"ID тикета: {channel.id}")
        await log_channel.send(embed=close_embed)
        
        # Отправляем файл с полным логом
        log_text = f"""=== ПОЛНЫЙ ЛОГ ТИКЕТА ===
ID тикета: {channel.id}
Создан: {ticket_info['created_at'].strftime('%Y-%m-%d %H:%M:%S')}
Закрыт: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Пользователь: {ticket_info['user_name']} (ID: {ticket_info['user_id']})
Тема: {ticket_info['topic']}
Закрыл: {closer.name if hasattr(closer, 'name') else 'Auto'}
Причина: {reason}
========================

=== ИСТОРИЯ СООБЩЕНИЙ ===
"""
        
        # Добавляем все сообщения
        full_messages = []
        async for msg in channel.history(limit=500, oldest_first=True):
            full_messages.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author.name} ({msg.author.id}): {msg.content}")
        
        log_text += "\n".join(full_messages)
        
        # Сохраняем и отправляем файл
        filename = f"ticket_log_{channel.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(log_text)
        
        await log_channel.send(file=discord.File(filename))
        os.remove(filename)
    
    # Сохраняем историю в JSON файл
    save_ticket_history()
    
    # Удаляем тикет из активных
    del tickets[channel.id]
    
    # Удаляем канал
    await channel.delete()

def save_ticket_history():
    """Сохраняет историю тикетов в JSON файл"""
    try:
        with open('ticket_history.json', 'w', encoding='utf-8') as f:
            # Конвертируем datetime в строки
            history_data = {}
            for ticket_id, info in ticket_history.items():
                history_data[str(ticket_id)] = {
                    'user_id': info['user_id'],
                    'user_name': info['user_name'],
                    'topic': info['topic'],
                    'created_at': info['created_at'].isoformat(),
                    'closed_at': info['closed_at'].isoformat() if info['closed_at'] else None,
                    'closed_by': info['closed_by'],
                    'close_reason': info['close_reason'],
                    'staff_members': info['staff_members'],
                    'messages': info['messages'][-50:]  # Сохраняем последние 50 сообщений
                }
            json.dump(history_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения истории: {e}")

def load_ticket_history():
    """Загружает историю тикетов из JSON файла"""
    try:
        if os.path.exists('ticket_history.json'):
            with open('ticket_history.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                for ticket_id, info in data.items():
                    ticket_history[int(ticket_id)] = {
                        'user_id': info['user_id'],
                        'user_name': info['user_name'],
                        'topic': info['topic'],
                        'created_at': datetime.fromisoformat(info['created_at']),
                        'closed_at': datetime.fromisoformat(info['closed_at']) if info['closed_at'] else None,
                        'closed_by': info['closed_by'],
                        'close_reason': info['close_reason'],
                        'staff_members': info['staff_members'],
                        'messages': info['messages']
                    }
    except Exception as e:
        print(f"Ошибка загрузки истории: {e}")

@bot.event
async def on_ready():
    print(f'Бот {bot.user} успешно запущен!')
    
    # Загружаем историю
    load_ticket_history()
    
    # Проверка истекающих тикетов при запуске
    for channel_id, ticket_info in list(tickets.items()):
        if ticket_info['status'] == 'open' and datetime.now() >= ticket_info['closing_time']:
            channel = bot.get_channel(channel_id)
            if channel:
                await close_ticket(channel, bot.user, "Автоматическое закрытие при запуске бота")
    
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

@bot.event
async def on_message(message):
    # Обработка сообщений в тикетах для логирования
    if message.channel.id in tickets:
        # Добавляем сообщение в историю тикета
        if message.author.id != bot.user.id:
            tickets[message.channel.id]['messages'].append({
                'author': message.author.name,
                'author_id': message.author.id,
                'content': message.content[:200],
                'timestamp': datetime.now().isoformat()
            })
            
            # Отмечаем персонал в тикете
            if message.author.guild_permissions.administrator or message.author.get_role(STAFF_ROLE_ID):
                if message.author.id not in tickets[message.channel.id]['staff_members']:
                    tickets[message.channel.id]['staff_members'].append(message.author.id)
    
    await bot.process_commands(message)

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
        color=0x3498db,
        timestamp=datetime.now()
    )
    embed.add_field(name="🟢 Открытых тикетов", value=len(open_tickets), inline=True)
    embed.add_field(name="🔴 Закрытых тикетов", value=len(closed_tickets), inline=True)
    embed.add_field(name="📋 Всего в истории", value=len(ticket_history), inline=True)
    
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
    
    # Статистика по типам тикетов
    topics = {}
    for ticket in ticket_history.values():
        topic = ticket['topic']
        topics[topic] = topics.get(topic, 0) + 1
    
    if topics:
        topic_stats = ""
        for topic, count in sorted(topics.items(), key=lambda x: x[1], reverse=True):
            topic_stats += f"- {topic}: {count}\n"
        embed.add_field(name="📈 Статистика по типам", value=topic_stats, inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='ticket_logs')
@commands.has_permissions(administrator=True)
async def ticket_logs(ctx, ticket_id: int = None):
    """Показать логи конкретного тикета"""
    if ticket_id is None:
        # Показываем последние 5 закрытых тикетов
        recent_tickets = list(ticket_history.items())[-5:]
        embed = discord.Embed(
            title="📋 Последние закрытые тикеты",
            color=0x3498db
        )
        for tid, info in recent_tickets:
            channel = bot.get_channel(tid)
            embed.add_field(
                name=f"Тикет #{tid}",
                value=f"👤 {info['user_name']}\n📂 {info['topic']}\n🔒 {info['closed_by'] if info['closed_by'] else 'Auto'}\n📅 {info['closed_at'].strftime('%d.%m.%Y %H:%M') if info['closed_at'] else 'Не закрыт'}",
                inline=False
            )
        await ctx.send(embed=embed)
    else:
        # Показываем конкретный тикет
        if ticket_id in ticket_history:
            info = ticket_history[ticket_id]
            embed = discord.Embed(
                title=f"📋 Детали тикета #{ticket_id}",
                color=0x3498db,
                timestamp=info['created_at']
            )
            embed.add_field(name="👤 Пользователь", value=f"{info['user_name']} (ID: {info['user_id']})", inline=False)
            embed.add_field(name="📂 Тема", value=info['topic'], inline=True)
            embed.add_field(name="📅 Создан", value=info['created_at'].strftime('%d.%m.%Y %H:%M'), inline=True)
            embed.add_field(name="🔒 Закрыт", value=info['closed_at'].strftime('%d.%m.%Y %H:%M') if info['closed_at'] else "Открыт", inline=True)
            embed.add_field(name="👥 Закрыл", value=info['closed_by'] if info['closed_by'] else "Не закрыт", inline=True)
            embed.add_field(name="📝 Причина", value=info['close_reason'] if info['close_reason'] else "Не указана", inline=False)
            
            if info['staff_members']:
                staff_names = []
                for staff_id in info['staff_members']:
                    staff = bot.get_user(staff_id)
                    if staff:
                        staff_names.append(staff.name)
                if staff_names:
                    embed.add_field(name="👥 Персонал", value=", ".join(staff_names), inline=False)
            
            await ctx.send(embed=embed)
        else:
            await ctx.send("Тикет с таким ID не найден в истории!")

# Запуск бота
bot.run(TOKEN)