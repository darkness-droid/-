import os
import threading
from flask import Flask
import discord
from discord.ext import commands

# ==== 1. 创建 Flask 健康检查服务 ====
app = Flask(__name__)

@app.route("/")
@app.route("/health")
def health():
    return "OK", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# 在后台线程启动 Web 服务
threading.Thread(target=run_web, daemon=True).start()

# ==== 2. 你的 Discord bot 代码 ====
intents = discord.Intents.default()
intents.message_content = True  # 如果需要读消息内容

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}") # 改为 bot.user
    print(f"Bot ID: {bot.user.id}")

# 这里放你原来的命令和事件
# @bot.command()
# async def ping(ctx):
#     await ctx.send("pong")

# ==== 3. 启动 bot ====
bot.run(os.environ["MTU1MDE4MDI5ODM2NzQ0MzA2NQ.GOj6k0.4OgrQ1TzjMp3tfPw6PIJ27FwgCkYxXB1glP3uA"])