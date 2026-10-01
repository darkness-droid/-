import os
import re
import asyncio
import random
import time
import threading
import discord
from discord.ext import commands
from flask import Flask
from google import genai
from google.genai import types

# ==================== 🌐 Flask 健康检查（给 Render 用） ====================
app = Flask(__name__)


@app.route("/")
@app.route("/health")
def health():
    return "OK", 200


def run_web():
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 [Web] Health check server running on port {port}")
    app.run(host="0.0.0.0", port=port)


threading.Thread(target=run_web, daemon=True).start()
# =========================================================================

# ==================== 🛠️ 凭证配置 ====================
DISCORD_TOKEN = "MTU1MDE4MDI5ODM2NzQ0MzA2NQ.GOj6k0.4OgrQ1TzjMp3tfPw6PIJ27FwgCkYxXB1glP3uA"

GEMINI_API_KEYS = [
    "AQ.Ab8RN6KJ28iviK8BpaQesaPqgFRBhHMIISOquQ1I48KPqcek-Q",
    "AQ.Ab8RN6IC8Li78z5Zw2neoOwBhtpDFBzZbFEen3a3rN87vdqYXA",
    "AQ.Ab8RN6IP5e_kftULq2wQo0i-eHFAIzLRpwEjklLM7cRN2dr2gQ",
]
# ======================================================================

# ==================== 🔑 多 Key 顺序消耗 + 自动切换 ====================
ai_clients = [genai.Client(api_key=k) for k in GEMINI_API_KEYS if k and k.strip()]
print(f"🔑 [启动] 已加载 {len(ai_clients)} 个 Gemini API Key（顺序消耗制）")

_active_client_index = 0
_client_lock = threading.Lock()


def get_active_client():
    with _client_lock:
        idx = min(_active_client_index, len(ai_clients) - 1)
        return ai_clients[idx]


def get_active_key_label() -> str:
    with _client_lock:
        return f"Key#{min(_active_client_index, len(ai_clients) - 1) + 1}"


def switch_to_next_client() -> bool:
    global _active_client_index
    with _client_lock:
        if _active_client_index + 1 < len(ai_clients):
            _active_client_index += 1
            print(f"🔑 [Key 切换] 已切换到第 {_active_client_index + 1} 个 API Key")
            return True
        print("❌ [Key 切换] 所有 API Key 都已用尽，无更多备用")
        return False


KEY_EXHAUSTED_MARKERS = (
    "resource_exhausted", "resource exhausted", "quota", "429",
    "rate limit", "rate_limit", "ratelimit", "too many requests",
    "permission_denied", "api key not valid", "api_key_invalid",
    "invalid api key", "exceeded your current quota", "billing", "credit",
)


def _is_key_exhausted(err: Exception) -> bool:
    s = str(err).lower()
    return any(m in s for m in KEY_EXHAUSTED_MARKERS)
# ======================================================================

# ==================== 📖 人设加载 ====================
def load_prompt_file(filename, fallback_text):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read().strip()
                print(f"📖 [人设载入] 成功从外部文件读取了: {filename} ({len(content)}字)")
                return content
        except Exception as e:
            print(f"⚠️ 读取 {filename} 失败，已启用代码内备用简短人设。原因: {e}")
    else:
        print(f"⚠️ 找不到外部文件 {filename}，已自动启用代码内默认备用人设。")
    return fallback_text


# 叶瞬光 —— 唯一人格
YE_SHUNGUANG_PROMPT = load_prompt_file(
    "prompt_normal.txt",
    "你现在是叶瞬光。用温柔、自然、真实的语气和对方对话，绝对不承认自己是 AI。"
)


def get_personality_config(prompt_text):
    return types.GenerateContentConfig(
        system_instruction=prompt_text,
        temperature=0.6,
    )
# ======================================================================

# ==================== 🔁 模型回退与重试机制 ====================
MODEL_CANDIDATES = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
]

RETRYABLE_CODES = ("503", "500", "502", "504", "UNAVAILABLE", "OVERLOADED", "high demand")


def _is_retryable(err: Exception) -> bool:
    s = str(err)
    return any(code in s for code in RETRYABLE_CODES)


async def safe_send_message(session, contents, max_retries=1):
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            return await session.send_message(contents)
        except Exception as e:
            last_err = e
            if not _is_retryable(e):
                raise
            wait = (3 * (2 ** attempt)) + random.uniform(0, 2)
            print(f"⏳ [Gemini 重试] 第 {attempt + 1}/{max_retries} 次失败，"
                  f"{wait:.2f}s 后再试... {str(e)[:120]}")
            await asyncio.sleep(wait)
    raise last_err


def create_chat_session(prompt_text, client=None):
    if client is None:
        client = get_active_client()

    last_err = None
    for model_name in MODEL_CANDIDATES:
        try:
            session = client.aio.chats.create(
                model=model_name,
                config=get_personality_config(prompt_text),
            )
            print(f"✅ [模型] 使用 {model_name} | {get_active_key_label()}")
            return session, model_name, client
        except Exception as e:
            last_err = e
            print(f"⚠️ [模型] {model_name} 创建失败，试下一个... 原因: {e}")
    raise RuntimeError(f"所有备用模型都不可用: {last_err}")


async def send_with_model_fallback(channel_id, contents):
    chat = channel_chats.get(channel_id)
    if not chat:
        raise RuntimeError("channel not initialized")

    last_err = None

    for _ in range(len(ai_clients)):
        client = get_active_client()
        key_exhausted = False

        for model_name in MODEL_CANDIDATES:
            try:
                session = client.aio.chats.create(
                    model=model_name,
                    config=get_personality_config(YE_SHUNGUANG_PROMPT),
                )
                resp = await safe_send_message(session, contents, max_retries=1)
                channel_chats[channel_id]['session'] = session
                channel_chats[channel_id]['model'] = model_name
                channel_chats[channel_id]['client'] = client
                return resp, model_name
            except Exception as e:
                last_err = e

                if _is_key_exhausted(e):
                    print(f"🔑 [Key 耗尽] {str(e)[:120]}")
                    key_exhausted = True
                    break

                if not _is_retryable(e):
                    raise
                print(f"⚠️ [模型 {model_name}] 不可用，尝试下一个... {str(e)[:100]}")
                continue

        if key_exhausted:
            if not switch_to_next_client():
                break
        else:
            break

    raise last_err
# ======================================================================

# ==================== 🤖 Bot 初始化 ====================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

channel_chats = {}
channel_language = {}

MAX_CHANNEL_CHATS = 100
DISCORD_LIMIT = 1900

# ==================== 🛡️ Discord 全局限流保护 ====================
DISCORD_SEND_LOCK = asyncio.Lock()
_last_discord_send_ts = 0.0
DISCORD_MIN_GAP = 1.2
GLOBAL_RATE_LIMIT_UNTIL = 0.0
# ==============================================================


def get_or_create_channel(channel_id):
    if channel_id not in channel_chats:
        if len(channel_chats) >= MAX_CHANNEL_CHATS:
            oldest_key = next(iter(channel_chats))
            del channel_chats[oldest_key]
            print(f"🧹 [清理] 频道数达到上限 {MAX_CHANNEL_CHATS}，已移除最旧频道: {oldest_key}")

        session, model_used, client_used = create_chat_session(YE_SHUNGUANG_PROMPT)
        channel_chats[channel_id] = {
            'session': session,
            'model': model_used,
            'client': client_used,
        }
    return channel_chats[channel_id]


async def safe_send(message, text, max_retries=3):
    global _last_discord_send_ts, GLOBAL_RATE_LIMIT_UNTIL

    text = (text or "……").strip() or "……"

    chunks = []
    remaining = text
    while remaining:
        chunks.append(remaining[:DISCORD_LIMIT])
        remaining = remaining[DISCORD_LIMIT:]
    if not chunks:
        chunks = ["……"]

    now = time.time()
    if now < GLOBAL_RATE_LIMIT_UNTIL:
        wait = GLOBAL_RATE_LIMIT_UNTIL - now
        print(f"⏳ [Discord 全局冷却中] 还需等待 {wait:.1f}s...")
        await asyncio.sleep(wait)

    for idx, chunk in enumerate(chunks):
        async with DISCORD_SEND_LOCK:
            now = time.time()
            gap = now - _last_discord_send_ts
            if gap < DISCORD_MIN_GAP:
                await asyncio.sleep(DISCORD_MIN_GAP - gap)

            sent = False
            for attempt in range(max_retries + 1):
                try:
                    if idx == 0:
                        await message.reply(chunk)
                    else:
                        await message.channel.send(chunk)
                    sent = True
                    _last_discord_send_ts = time.time()
                    break

                except discord.HTTPException as e:
                    _last_discord_send_ts = time.time()

                    if e.status == 429:
                        err_text = str(e).lower()
                        is_global = (
                            "global rate limit" in err_text
                            or "being blocked" in err_text
                            or "exceeding global" in err_text
                        )
                        retry_after = getattr(e, 'retry_after', None)

                        if is_global:
                            base = float(retry_after) if retry_after else 60.0
                            wait = max(base, 60.0) + random.uniform(2.0, 5.0)
                            GLOBAL_RATE_LIMIT_UNTIL = time.time() + wait
                            print(f"🚨 [Discord 全局限流] 触发 Cloudflare 级封禁，"
                                  f"进入 {wait:.1f}s 冷却...")
                            return
                        else:
                            base = float(retry_after) if retry_after else 1.0
                            wait = base + random.uniform(0.5, 1.5)
                            print(f"⏳ [Discord 频道限流] 等待 {wait:.1f}s 后重试...")
                            await asyncio.sleep(wait)
                            continue

                    elif e.status == 403:
                        print(f"❌ [Discord 403] 没有权限发送消息，放弃。")
                        return
                    elif e.status == 404:
                        print(f"❌ [Discord 404] 频道不存在或无权访问，放弃。")
                        return
                    else:
                        print(f"❌ [Discord 错误] status={e.status} | {e}")
                        return

                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    print(f"❌ [safe_send] 未知错误: {e}")
                    _last_discord_send_ts = time.time()
                    return

            if not sent:
                print(f"❌ [safe_send] 分段 {idx + 1} 重试 {max_retries + 1} 次仍失败，放弃")
                return
# ======================================================================


@bot.event
async def on_ready():
    print(f"✨ {bot.user} 登录成功！")
    print(f"🗣️ 人格: 叶瞬光")
    print(f"🔑 API Key 池: 共 {len(ai_clients)} 个 | 当前使用 {get_active_key_label()}")
    print(f"🔁 模型回退顺序: {' → '.join(MODEL_CANDIDATES)}")
    print(f"🌐 指令: !english / !resetlanguage")
    print("----------------------------------------")


# 🌐 语言命令一：整个频道切换为英文模式
@bot.command(name="english")
async def set_english(ctx):
    channel_language[ctx.channel.id] = 'en'
    await ctx.reply(
        "🌐 好！从现在开始，**这个频道里所有人**都会收到**纯英文**回复。\n"
        "（想切回华语请输入 `!resetlanguage`）"
    )


# 🌐 语言命令二：整个频道切换回华语模式
@bot.command(name="resetlanguage")
async def reset_language(ctx):
    channel_language[ctx.channel.id] = 'zh'
    await ctx.reply(
        "🌐 好！从现在开始，**这个频道里所有人**都会收到**纯华语**回复。\n"
        "（想再切英文请输入 `!english`）"
    )


# ==================== 主消息处理 ====================
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # 🛡️ 全局冷却期内，直接忽略所有消息
    if time.time() < GLOBAL_RATE_LIMIT_UNTIL:
        remain = GLOBAL_RATE_LIMIT_UNTIL - time.time()
        print(f"⏳ [全局冷却] 忽略消息 | 还剩 {remain:.1f}s | 来自 {message.author.display_name}")
        return

    if message.mention_everyone:
        return

    if message.content.startswith('!'):
        await bot.process_commands(message)
        return

    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        user_input = message.content.replace(f'<@{bot.user.id}>', '').strip()

        if not user_input:
            await message.reply("？你叫我了但没说话……")
            return

        channel_id = message.channel.id

        try:
            get_or_create_channel(channel_id)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"❌ [频道初始化失败] {e}")
            try:
                await message.reply("……我连不上模型，等一下再试好不好？")
            except Exception:
                pass
            return

        current_language = channel_language.get(channel_id, 'zh')

        async with message.channel.typing():
            try:
                # 🌐 语言指令
                if current_language == 'en':
                    language_note = (
                        "╔══════════════════════════════════════════════════════╗\n"
                        "║ 🌐【ENGLISH MODE｜强制生效｜只准输出英文】🌐         ║\n"
                        "╚══════════════════════════════════════════════════════╝\n"
                        "【语言指令｜最高优先级】\n"
                        "  ✅ 你现在必须 100% 使用【英文】回复。\n"
                        "  ✅ 绝对不可以在回复里出现任何【中文字符】。\n"
                        "\n"
                        "【🚫 绝对禁止｜最重要】\n"
                        "  ❌ 不要中英混搭，不要翻译一半。\n"
                        "  ❌ 不要输出「英文版 + 中文版」两段。\n"
                        "  ❌ 不要附上中文翻译。\n"
                        "  ✅ 一次回复里，只准出现【一种语言】，就是英文。\n"
                    )
                else:
                    language_note = (
                        "╔══════════════════════════════════════════════════════╗\n"
                        "║ 🌐【华语模式｜只准输出中文】🌐                      ║\n"
                        "╚══════════════════════════════════════════════════════╝\n"
                        "【语言指令｜最高优先级】\n"
                        "  ✅ 当前频道处于【华语模式】，请用中文回复。\n"
                        "\n"
                        "【🚫 绝对禁止｜最重要】\n"
                        "  ❌ 不要输出「中文版 + 英文版」两段。\n"
                        "  ❌ 不要附上英文翻译。\n"
                        "  ✅ 一次回复里，只准出现【一种语言】，就是中文。\n"
                    )

                final_prompt = (
                    f"{language_note}\n"
                    f"【用户的名字】{message.author.display_name}\n"
                    f"【用户对你说的话】\n{user_input}"
                )

                # ==================== 🚀 发送（带模型 & Key 回退） ====================
                try:
                    response, used_model = await send_with_model_fallback(
                        channel_id, [final_prompt]
                    )
                except Exception as api_e:
                    import traceback
                    print(f"❌ [Gemini API] 所有模型 & Key 都调用失败 | 用户={message.author.display_name}")
                    print(f"❌ [Gemini API] 异常类型: {type(api_e).__name__}")
                    print(f"❌ [Gemini API] 异常信息: {api_e}")
                    traceback.print_exc()
                    if _is_key_exhausted(api_e):
                        await safe_send(message, "……我的 API 额度用完了，请补充新的 Key。")
                    elif _is_retryable(api_e):
                        await safe_send(message, "……那边说现在太忙了，等一下再说话好不好？")
                    else:
                        await safe_send(message, "……刚刚出了点问题，你再说一遍？")
                    return
                # ================================================================

                raw_text = response.text if response is not None else None
                if raw_text is None:
                    print("⚠️ [AI] response.text 为 None，使用兜底文本")
                    raw_text = "……"

                print("🤖 [AI原始回复]:")
                print(raw_text)
                print("----------------------------------------")

                await safe_send(message, raw_text)

            except discord.Forbidden:
                print("❌ 警告：没有权限查看历史或发送消息。")
                try:
                    await message.reply("……我好像没有权限说话，检查一下频道设置？")
                except Exception:
                    pass
            except Exception as e:
                import traceback
                print("=" * 60)
                print(f"❌ [主错误] 用户={message.author.display_name} (ID: {message.author.id})")
                print(f"❌ [主错误] 异常类型: {type(e).__name__}")
                print(f"❌ [主错误] 异常信息: {e}")
                traceback.print_exc()
                print("=" * 60)
                try:
                    await message.reply("……出了点问题，你再说一遍？")
                except Exception:
                    pass


# 启动机器人
bot.run(DISCORD_TOKEN)
