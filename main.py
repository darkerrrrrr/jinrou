import discord, os
from discord.ext import commands
from config import game

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def setup_hook(): await bot.load_extension("cogs.game")

@bot.event
async def on_message(message):
    if message.author.bot or message.guild:
        await bot.process_commands(message); return
    if game.is_playing and message.author in game.alive_players:
        role = game.roles.get(message.author)
        if role and role.name == "人狼":
            for member in game.alive_players:
                if member != message.author and game.roles.get(member).name == "人狼":
                    try: await member.send(f"💬 [人狼チャット] {message.author.display_name}: {message.content}")
                    except: pass
    await bot.process_commands(message)

bot.run(os.getenv("DISCORD_BOT_TOKEN"))