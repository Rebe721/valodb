import os
import json
import random
import asyncio
import datetime
import logging
from threading import Thread
from zoneinfo import ZoneInfo
import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# -------------------------------
# ログの設定
logging.basicConfig(level=logging.INFO)

# -------------------------------
# Googleスプレッドシートの認証設定
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials_info = json.loads(os.getenv("CREDENTIALS_JSON"))
credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
gc = gspread.authorize(credentials)
sheet = gc.open("Accounts").sheet1  # スプレッドシート名を指定

# -------------------------------
# Discord Bot の設定
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True       # メンバー情報取得用
intents.voice_states = True  # ボイス関連イベント用
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree  # スラッシュコマンド管理用

# -------------------------------
# タイムゾーンの設定（東京）
TOKYO_TZ = ZoneInfo("Asia/Tokyo")

# -------------------------------
# アカウント管理用変数
# borrowed_accounts: {user_id: {"account": account_data, "task": task, "guild_id": guild_id, "channel_id": channel_id}}
borrowed_accounts = {}
user_status = {}

# -------------------------------
# カスタムモーダルクラス（アカウント登録用）
class AccountRegisterModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="アカウント登録フォーム")
        self.add_item(discord.ui.TextInput(
            label="Name",
            placeholder="例: Tanaka Taro",
            custom_id="account-name",
            required=True
        ))
        self.add_item(discord.ui.TextInput(
            label="ID",
            placeholder="例: user123",
            custom_id="account-id",
            required=True
        ))
        self.add_item(discord.ui.TextInput(
            label="Password",
            placeholder="例: ******",
            custom_id="account-password",
            required=True
        ))
        self.add_item(discord.ui.TextInput(
            label="Rank",
            placeholder="例: Beginner",
            custom_id="account-rank",
            required=True
        ))

    async def on_submit(self, interaction: discord.Interaction):
        name = self.children[0].value
        account_id = self.children[1].value
        password = self.children[2].value
        rank = self.children[3].value

        try:
            sheet.append_row([name, account_id, password, rank, "available"])
        except Exception as e:
            logging.error(f"スプレッドシートへの書き込みエラー: {e}")
            await interaction.response.send_message("アカウントの登録に失敗しました。", ephemeral=True)
            return

        await interaction.response.send_message(
            f"アカウント **{name}** を登録しました！", ephemeral=True
        )

# /register コマンド
@tree.command(name="register", description="新しいアカウントを登録します")
async def register(interaction: discord.Interaction):
    await interaction.response.send_modal(AccountRegisterModal())

# -------------------------------
# 自動返却タスク（5時間後に自動返却）
async def auto_return_account(user_id: int, account: dict, guild_id: int, channel_id: int):
    await asyncio.sleep(5 * 60 * 60)  # 5時間待機
    try:
        logging.info(f"自動返却処理開始: User ID={user_id}, Account={account['name']}")
        sheet.update_cell(account["row"], 5, "available")
        borrowed_accounts.pop(user_id, None)
        user_status.pop(user_id, None)
        guild = bot.get_guild(guild_id)
        if guild is None:
            logging.error(f"Guild ID {guild_id} が見つかりません。")
            return
        channel = guild.get_channel(channel_id)
        if channel is None:
            logging.error(f"Channel ID {channel_id} がGuild ID {guild_id}内に見つかりません。")
            return
        user = guild.get_member(user_id)
        if user is None:
            logging.error(f"User ID {user_id} がGuild ID {guild_id}内に見つかりません。")
            return

        await channel.send(
            f"{user.mention} の **{account['name']}** に自動返却処理を行いました。"
        )
        logging.info(f"自動返却処理完了: User ID={user_id}, Account={account['name']}")
    except Exception as e:
        logging.error(f"自動返却中にエラーが発生しました: {e}")

# -------------------------------
# /use_account コマンド（アカウント借用）
@tree.command(name="use_account", description="アカウントを借りる")
async def use_account(interaction: discord.Interaction):
    if interaction.user.id in user_status:
        await interaction.response.send_message(
            "すでにアカウントを借りています。返却してください。",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    try:
        accounts = sheet.get_all_records()
    except Exception as e:
        logging.error(f"スプレッドシートからデータ取得中にエラーが発生しました: {e}")
        await interaction.followup.send(
            "スプレッドシートからデータを取得できませんでした。後でもう一度試してください。",
            ephemeral=True
        )
        return

    available_accounts = [
        {**acc, "row": index + 2}
        for index, acc in enumerate(accounts)
        if acc["status"] == "available"
    ]

    if not available_accounts:
        await interaction.followup.send(
            "利用可能なアカウントがありません。",
            ephemeral=True
        )
        return

    options = [
        discord.SelectOption(label=f"{acc['name']} ({acc['rank']})", value=acc["name"])
        for acc in available_accounts
    ]

    class AccountDropdown(discord.ui.Select):
        def __init__(self):
            super().__init__(placeholder="アカウントを選択してください", options=options)

        async def callback(self, interaction: discord.Interaction):
            selected_account = next(
                acc for acc in available_accounts if acc["name"] == self.values[0]
            )
            try:
                sheet.update_cell(selected_account["row"], 5, "borrowed")
            except Exception as e:
                logging.error(f"スプレッドシートの状態更新中にエラーが発生しました: {e}")
                await interaction.response.send_message(
                    "アカウントの状態を更新できませんでした。後でもう一度試してください。",
                    ephemeral=True
                )
                return

            user_status[interaction.user.id] = True
            borrowed_accounts[interaction.user.id] = {
                "account": selected_account,
                "task": None,
                "guild_id": interaction.guild.id,
                "channel_id": interaction.channel.id
            }

            guild_id = interaction.guild.id if interaction.guild else None
            channel_id = interaction.channel.id if interaction.channel else None
            if guild_id is None or channel_id is None:
                await interaction.response.send_message(
                    "サーバー情報の取得に失敗しました。管理者に連絡してください。",
                    ephemeral=True
                )
                return

            task = asyncio.create_task(auto_return_account(interaction.user.id, selected_account, guild_id, channel_id))
            borrowed_accounts[interaction.user.id]["task"] = task

            return_time = datetime.datetime.now(TOKYO_TZ) + datetime.timedelta(hours=5)
            return_time_str = return_time.strftime('%Y-%m-%d %H:%M:%S %Z')
            account_details = (
                f"**アカウント情報:**\n"
                f"**Name:** {selected_account['name']}\n"
                f"**ID:** {selected_account['id']}\n"
                f"**Password:** {selected_account['password']}\n"
                f"**Rank:** {selected_account['rank']}\n"
                f"**返却期限:** {return_time_str}\n"
            )
            await interaction.response.send_message(account_details, ephemeral=True)
            await interaction.channel.send(
                f"{interaction.user.mention} が **{selected_account['name']}** を借りました！"
            )

    view = discord.ui.View()
    view.add_item(AccountDropdown())
    await interaction.followup.send("アカウントを選択してください:", view=view, ephemeral=True)

# -------------------------------
# /return_account コマンド（アカウント返却）
@tree.command(name="return_account", description="アカウントを返却する")
async def return_account(interaction: discord.Interaction):
    if interaction.user.id not in borrowed_accounts:
        await interaction.response.send_message("返却するアカウントがありません。", ephemeral=True)
        return

    account_info = borrowed_accounts.get(interaction.user.id)
    account = account_info["account"]
    task = account_info["task"]
    guild_id = account_info.get("guild_id")
    channel_id = account_info.get("channel_id")

    # 状態チェック（不整合の場合はリセット）
    if not account or sheet.cell(account["row"], 5).value != "borrowed":
        borrowed_accounts.pop(interaction.user.id, None)
        user_status.pop(interaction.user.id, None)
        if task:
            task.cancel()
        await interaction.response.send_message(
            "アカウントの借用状態が不整合でしたが、自動的にリセットしました。再度借用してください。",
            ephemeral=True
        )
        return

    if task:
        task.cancel()

    class RankUpdateModal(discord.ui.Modal):
        def __init__(self):
            super().__init__(title="ランク更新")
            self.add_item(discord.ui.TextInput(
                label="新しいランクを入力 (例: Intermediate)",
                placeholder="変更がなければ同じランクを入力してください",
                default=account["rank"],
                custom_id="new-rank",
                required=True
            ))

        async def on_submit(self, interaction: discord.Interaction):
            new_rank = self.children[0].value
            if new_rank != account["rank"]:
                try:
                    sheet.update_cell(account["row"], 4, new_rank)
                except Exception as e:
                    logging.error(f"スプレッドシートのランクセル更新中にエラーが発生しました: {e}")
                    await interaction.response.send_message(
                        "ランクの更新に失敗しました。後でもう一度試してください。",
                        ephemeral=True
                    )
                    return
            try:
                sheet.update_cell(account["row"], 5, "available")
            except Exception as e:
                logging.error(f"スプレッドシートの状態更新中にエラーが発生しました: {e}")
                await interaction.response.send_message(
                    "アカウントの状態を更新できませんでした。後でもう一度試してください。",
                    ephemeral=True
                )
                return

            borrowed_accounts.pop(interaction.user.id, None)
            user_status.pop(interaction.user.id, None)
            guild = bot.get_guild(guild_id)
            if guild is None:
                logging.error(f"Guild ID {guild_id} が見つかりません。")
                await interaction.response.send_message(
                    f"アカウント **{account['name']}** を返却しました。\n**新しいランク:** {new_rank}",
                    ephemeral=True
                )
                return
            channel = guild.get_channel(channel_id)
            if channel is None:
                logging.error(f"Channel ID {channel_id} がGuild ID {guild_id}内に見つかりません。")
                await interaction.response.send_message(
                    f"アカウント **{account['name']}** を返却しました。\n**新しいランク:** {new_rank}",
                    ephemeral=True
                )
                return
            user = guild.get_member(interaction.user.id)
            if user is None:
                logging.error(f"User ID {interaction.user.id} がGuild ID {guild_id}内に見つかりません。")
                await interaction.response.send_message(
                    f"アカウント **{account['name']}** を返却しました。\n**新しいランク:** {new_rank}",
                    ephemeral=True
                )
                return

            await interaction.response.send_message(
                f"アカウント **{account['name']}** を返却しました。\n**新しいランク:** {new_rank}",
                ephemeral=True
            )
            await channel.send(
                f"{user.mention} が **{account['name']}** を返却しました！\n**更新後のランク:** {new_rank}"
            )

    modal = RankUpdateModal()
    await interaction.response.send_modal(modal)

# -------------------------------
# /remove_comment コマンド（コメント削除）
@tree.command(name="remove_comment", description="コードブロック、画像、ファイルを除くコメントを削除します。")
async def remove_comment(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("このコマンドを使用する権限がありません。", ephemeral=True)
        return

    await interaction.response.defer()

    channel = interaction.channel
    now = datetime.datetime.now(datetime.timezone.utc)
    bulk_deletable_messages = []
    async_deletable_messages = []

    async for message in channel.history(limit=100):
        if not message.attachments and "```" not in message.content and not message.embeds:
            if (now - message.created_at).days <= 14:
                bulk_deletable_messages.append(message)
            else:
                async_deletable_messages.append(message)

    bulk_deleted_count = 0
    if bulk_deletable_messages:
        try:
            await channel.delete_messages(bulk_deletable_messages)
            bulk_deleted_count = len(bulk_deletable_messages)
        except Exception as e:
            logging.error(f"一括削除中にエラーが発生しました: {e}")

    async_deleted_count = 0
    for message in async_deletable_messages:
        try:
            await message.delete()
            async_deleted_count += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            logging.error(f"個別削除中にエラーが発生しました: {e}")

    total_deleted = bulk_deleted_count + async_deleted_count
    await interaction.followup.send(
        f"削除が完了しました！\n- 一括削除: {bulk_deleted_count} 件\n- 個別削除: {async_deleted_count} 件\n- 合計: {total_deleted} 件"
    )

# -------------------------------
# /reset_borrowed コマンド（管理者専用：借用状態の手動リセット）
@tree.command(name="reset_borrowed", description="借用状態を手動でリセットします（管理者専用）")
async def reset_borrowed(interaction: discord.Interaction, user_id: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("このコマンドを使用する権限がありません。", ephemeral=True)
        return

    try:
        user_id_int = int(user_id)
        if user_id_int in borrowed_accounts:
            account_info = borrowed_accounts.pop(user_id_int)
            user_status.pop(user_id_int, None)
            task = account_info.get("task")
            if task:
                task.cancel()
            await interaction.response.send_message(f"ユーザーID {user_id} の借用状態をリセットしました。", ephemeral=True)
        else:
            await interaction.response.send_message(f"ユーザーID {user_id} は借用状態ではありません。", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("正しいユーザーIDを入力してください。", ephemeral=True)

# -------------------------------
# 以下、スマスロカバネリ覚醒ゾーン再現用 /kabaneri コマンドの強化部分
# ※画像ファイルは app/kabaneri 内に配置している前提

# 調整用パラメータ
# 各リールの停止までの待機時間（各リールごとに、GIFから結果画像へ切り替えるまでの秒数）
REEL_STOP_DELAYS = [0.7, 1.4, 2.1]
# リール結果表示後から特別演出開始までの待機時間（秒）
SPECIAL_EFFECT_DELAY = 0.1

# 基本ディレクトリの絶対パス（環境に合わせて変更）
BASE_DIR = os.path.join("valodb", "app", "kabaneri")

# 各リールの初期状態は回転中の GIF 画像
REEL_GIFS = [
    os.path.join(BASE_DIR, "reel1_spin.gif"),
    os.path.join(BASE_DIR, "reel2_spin.gif"),
    os.path.join(BASE_DIR, "reel3_spin.gif")
]

# 各リールの停止時の画像（通常役とチャンス役）
REEL_FINAL_IMAGES = [
    {
        "normal": os.path.join(BASE_DIR, "reel_normal.png"),
        "chance": os.path.join(BASE_DIR, "reel1_chance.png")
    },
    {
        "normal": os.path.join(BASE_DIR, "reel_normal.png"),
        "chance": os.path.join(BASE_DIR, "reel2_chance.png")
    },
    {
        "normal": os.path.join(BASE_DIR, "reel_normal.png"),
        "chance": os.path.join(BASE_DIR, "reel3_chance.png")
    }
]

# 特別な当選演出用GIF
SPECIAL_WIN_GIF = os.path.join(BASE_DIR, "sp.gif")

# 再生する音声ファイル
ROKKON_AUDIO_FILE = os.path.join("valodb", "app", "kabaneri", "rokkon.mp3")
FFMPEG_PATH = "ffmpeg"

@tree.command(name="kabaneri", description="六根清浄！")
async def kabaneri(interaction: discord.Interaction):
    # ボイスチャンネル参加の確認
    if interaction.user.voice is None or interaction.user.voice.channel is None:
        await interaction.response.send_message(
            "あなたはボイスチャンネルに参加していません。先に通話に参加してください。",
            ephemeral=True
        )
        return

    voice_channel = interaction.user.voice.channel

    # 初期応答（defer）
    await interaction.response.defer()

    # 各リールの回転中GIFを順次送信
    reel_messages = []
    for i in range(3):
        file = discord.File(REEL_GIFS[i], filename=f"reel{i+1}_spin.gif")
        embed = discord.Embed(title=f"Reel {i+1}", description="回転中...")
        embed.set_image(url=f"attachment://reel{i+1}_spin.gif")
        message = await interaction.followup.send(embed=embed, file=file)
        reel_messages.append(message)

    # 各リールの停止タイミング（weightを指定：chance:1, normal:4 => chanceが1/5の確率）
    final_results = [None, None, None]
    for i, delay in enumerate(REEL_STOP_DELAYS):
        await asyncio.sleep(delay)
        result = random.choices(["chance", "normal"], weights=[1, 4])[0]
        final_results[i] = result

        final_image_path = REEL_FINAL_IMAGES[i][result]
        file = discord.File(final_image_path, filename=os.path.basename(final_image_path))
        embed = discord.Embed(
            title=f"Reel {i+1}",
            description=f"{'チャンス' if result == 'chance' else '通常'}"
        )
        embed.set_image(url=f"attachment://{os.path.basename(final_image_path)}")
        try:
            await reel_messages[i].edit(embed=embed, attachments=[file])
        except discord.errors.HTTPException as e:
            logging.error(f"メッセージ編集中にエラーが発生しました: {e}")
            await interaction.followup.send(
                "リールの停止中にエラーが発生しました。管理者に連絡してください。",
                ephemeral=True
            )
            return

    # リール結果表示後、SPECIAL_EFFECT_DELAY秒待機してから特別演出に移行
    await asyncio.sleep(SPECIAL_EFFECT_DELAY)

    # 最終判定：いずれかのリールで chance が出た場合に特別演出
    if any(result == "chance" for result in final_results):
        file = discord.File(SPECIAL_WIN_GIF, filename=os.path.basename(SPECIAL_WIN_GIF))
        embed = discord.Embed(title="!!!六根清浄!!!", description="!!!貫け!!!鋼の魂!!!")
        embed.set_image(url=f"attachment://{os.path.basename(SPECIAL_WIN_GIF)}")
        await interaction.followup.send(embed=embed, file=file)

        try:
            if interaction.guild.voice_client:
                voice_client = interaction.guild.voice_client
                if voice_client.channel != voice_channel:
                    await voice_client.move_to(voice_channel)
            else:
                voice_client = await voice_channel.connect()
            if voice_client.is_playing():
                voice_client.stop()
            audio_source = discord.FFmpegPCMAudio(ROKKON_AUDIO_FILE, executable=FFMPEG_PATH)
            voice_client.play(audio_source)
            while voice_client.is_playing():
                await asyncio.sleep(1)
            await voice_client.disconnect()
        except Exception as e:
            logging.error(f"音声再生中にエラーが発生しました: {e}")
            await interaction.followup.send("音声の再生中にエラーが発生しました。", ephemeral=True)
    else:
        result_text = "\n".join([
            f"Reel {i+1}: {'チャンス' if result == 'chance' else '通常'}"
            for i, result in enumerate(final_results)
        ])
        embed = discord.Embed(title="パチンコ・パチスロは適度に楽しむ遊びです", description="のめり込みに注意しましょう。")
        embed.add_field(name="リール結果", value=result_text, inline=False)
        await interaction.followup.send(embed=embed)

# -------------------------------
# Flaskアプリケーション（ヘルスチェック用）
app = Flask(__name__)

@app.route("/health")
def health_check():
    return "OK", 200

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# Flaskサーバーをバックグラウンドで起動
thread = Thread(target=run_flask)
thread.daemon = True
thread.start()

# Bot準備完了時の処理
@bot.event
async def on_ready():
    await tree.sync()
    logging.info(f"Logged in as {bot.user}")

# -------------------------------
# Bot の起動
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
