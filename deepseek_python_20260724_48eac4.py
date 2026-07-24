import discord
from discord.ext import commands
import os
from config import Config
from utils.database import Database
from utils.logger import Logger

# Настройка бота
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} успешно запущен!')
    print(f'📊 На сервере: {len(bot.guilds)} гильдий')
    
    # Загружаем коги
    await load_cogs()
    
    # Создаем основное сообщение
    await setup_main_message()

async def load_cogs():
    """Загрузка всех когов"""
    try:
        await bot.load_extension('cogs.tickets')
        print('✅ Cog tickets загружен')
    except Exception as e:
        print(f'❌ Ошибка загрузки cog: {e}')

async def setup_main_message():
    """Создание основного сообщения с тикетами"""
    guild = bot.get_guild(Config.GUILD_ID)
    if guild:
        ticket_channel = discord.utils.get(guild.text_channels, name="tickets")
        if ticket_channel:
            # Очищаем старые сообщения
            async for message in ticket_channel.history(limit=100):
                if message.author == bot.user:
                    await message.delete()
            
            # Создаем новое сообщение
            from cogs.tickets import TicketView
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
            
            view = TicketView(bot)
            await ticket_channel.send(embed=embed, view=view)
            print('✅ Основное сообщение создано!')

@bot.command(name='reload')
@commands.has_permissions(administrator=True)
async def reload_cogs(ctx):
    """Перезагрузка всех когов"""
    try:
        await bot.reload_extension('cogs.tickets')
        await ctx.send('✅ Коги перезагружены!')
    except Exception as e:
        await ctx.send(f'❌ Ошибка перезагрузки: {e}')

if __name__ == '__main__':
    bot.run(Config.BOT_TOKEN)