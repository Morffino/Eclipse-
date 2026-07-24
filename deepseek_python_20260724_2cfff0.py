import discord
from discord.ext import commands
import json
import os
from datetime import datetime

# Конфигурация
TOKEN = 'YOUR_BOT_TOKEN_HERE'
GUILD_ID = 123456789012345678  # ID вашего сервера
CATEGORY_ID = 123456789012345678  # ID категории для тикетов
STAFF_ROLE_ID = 123456789012345678  # ID роли персонала
LOG_CHANNEL_ID = 123456789012345678  # ID канала для логов

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
            'created_at': datetime.now()
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
        embed.set_footer(text=f"Тикет создан: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        
        await channel.send(f"{interaction.user.mention} {guild.get_role(STAFF_ROLE_ID).mention}", embed=embed)
        
        # Добавляем кнопки управления тикетом
        view = TicketControlView()
        await channel.send("**Управление тикетом:**", view=view)
        
        # Логирование
        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title="📩 Создан новый тикет",
                description=f"Пользователь: {interaction.user.mention}\nТема: {topic}\nКанал: {channel.mention}",
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
        
        # Удаляем тикет из словаря
        del tickets[channel.id]
        
        # Логирование
        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title="📪 Тикет закрыт",
                description=f"Закрыл: {interaction.user.mention}\nКанал: {channel.mention}",
                color=0xff0000
            )
            await log_channel.send(embed=log_embed)
        
        await interaction.response.send_message("Тикет будет закрыт через 5 секунд...")
        await channel.delete(delay=5)

@bot.event
async def on_ready():
    print(f'Бот {bot.user} успешно запущен!')
    
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
                value="02.07.2026 13:31\n\n**HS TICKET | Центр поддержки**\nНужна помощь, восстановление. Выбери подходящую тему кнопки обращения.\n\n**Важно:** создавайте текст только увидите нужная команда.",
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
        value="02.07.2026 13:31\n\n**HS TICKET | Центр поддержки**\nНужна помощь, восстановление. Выбери подходящую тему кнопки обращения.\n\n**Важно:** создавайте текст только увидите нужная команда.",
        inline=False
    )
    
    view = TicketView()
    await ctx.send(embed=embed, view=view)
    await ctx.message.delete()

@bot.command(name='add_ticket_channel')
@commands.has_permissions(administrator=True)
async def add_ticket_channel(ctx, channel_id: int):
    """Добавить канал для тикетов"""
    global TICKET_CHANNEL_ID
    TICKET_CHANNEL_ID = channel_id
    await ctx.send(f"Канал {channel_id} добавлен как канал для тикетов!")

@bot.event
async def on_error(event, *args, **kwargs):
    print(f"Произошла ошибка: {event}")

# Запуск бота
bot.run(TOKEN)