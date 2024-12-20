import os
import json
from oauth2client.service_account import ServiceAccountCredentials
import discord
from discord.ext import commands
from discord import app_commands
import gspread
from flask import Flask
import asyncio
import datetime

# GoogleスプレッドシートAPIのスコープ
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# 環境変数から認証情報を取得
credentials_info = json.loads(os.getenv("CREDENTIALS_JSON"))
credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)

# Googleスプレッドシートの設定
gc = gspread.authorize(credentials)
sheet = gc.open("Accounts").sheet1  # スプレッドシート名を設定

# Discord Botの設定
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree  # スラッシュコマンド用の管理クラス

# ユーザーの借用状態を保持
borrowed_accounts = {}
user_status = {}

# カスタムモーダルクラス
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

        # スプレッドシートに追加
        sheet.append_row([name, account_id, password, rank, "available"])
        await interaction.response.send_message(
            f"アカウント {name} を登録しました！", ephemeral=True
        )

# 登録コマンド
@tree.command(name="register", description="新しいアカウントを登録します")
async def register(interaction: discord.Interaction):
    await interaction.response.send_modal(AccountRegisterModal())

# アカウント選択コマンド
# アカウント選択コマンド (詳細情報の送信を追加)
@tree.command(name="use_account", description="アカウントを借りる")
async def use_account(interaction: discord.Interaction):
    if interaction.user.id in user_status:
        await interaction.response.send_message(
            "すでにアカウントを借りています。返却してください。", ephemeral=True
        )
        return

    # スプレッドシートデータを取得し、行番号を追加
    accounts = sheet.get_all_records()
    available_accounts = [
        {**acc, "row": index + 2}  # 行番号を計算 (ヘッダー行を考慮)
        for index, acc in enumerate(accounts)
        if acc["status"] == "available"
    ]

    if not available_accounts:
        await interaction.response.send_message(
            "利用可能なアカウントがありません。", ephemeral=True
        )
        return

    # プルダウンメニューを作成
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
            # 'row' を利用して行を更新
            sheet.update_cell(selected_account["row"], 5, "borrowed")
            borrowed_accounts[interaction.user.id] = selected_account
            user_status[interaction.user.id] = True

            # 選択したアカウントの詳細を表示
            account_details = (
                f"**アカウント情報:**\n"
                f"**Name:** {selected_account['name']}\n"
                f"**ID:** {selected_account['id']}\n"
                f"**Password:** {selected_account['password']}\n"
                f"**Rank:** {selected_account['rank']}\n"
            )
            await interaction.response.send_message(account_details, ephemeral=True)
            await interaction.channel.send(
                f"{interaction.user.name}が{selected_account['name']}を借りました！"
            )

    view = discord.ui.View()
    view.add_item(AccountDropdown())
    await interaction.response.send_message("アカウントを選択してください:", view=view, ephemeral=True)


# アカウント返却コマンド (ランク更新を追加)
@tree.command(name="return_account", description="アカウントを返却する")
async def return_account(interaction: discord.Interaction):
    # 借用状態を再確認
    if interaction.user.id not in borrowed_accounts:
        await interaction.response.send_message(
            "返却するアカウントがありません。", ephemeral=True
        )
        return

    account = borrowed_accounts.get(interaction.user.id)
    if not account or sheet.cell(account["row"], 5).value != "borrowed":
        # 状態が不整合な場合、自動修正
        borrowed_accounts.pop(interaction.user.id, None)
        user_status.pop(interaction.user.id, None)
        await interaction.response.send_message(
            "アカウントの借用状態が不整合でしたが、自動的にリセットしました。再度借用してください。",
            ephemeral=True
        )
        return

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
                # スプレッドシートのランクセルを更新
                sheet.update_cell(account["row"], 4, new_rank)

            sheet.update_cell(account["row"], 5, "available")
            borrowed_accounts.pop(interaction.user.id, None)  # 状態をリセット
            user_status.pop(interaction.user.id, None)  # ユーザーステータスを削除
            await interaction.response.send_message(
                f"アカウント {account['name']} を返却しました。\n**新しいランク:** {new_rank}",
                ephemeral=True
            )
            await interaction.channel.send(
                f"{interaction.user.name}が{account['name']}を返却しました！\n**更新後のランク:** {new_rank}"
            )

    # ランク更新モーダルを表示
    await interaction.response.send_modal(RankUpdateModal())

@tree.command(name="remove_comment", description="コードブロック、画像、ファイルを除くコメントを削除します。")
async def remove_comment(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("このコマンドを使用する権限がありません。", ephemeral=True)
        return

    await interaction.response.defer()  # 初期応答を送信し、処理を待機させる

    channel = interaction.channel
    now = datetime.datetime.now(datetime.timezone.utc)
    bulk_deletable_messages = []
    async_deletable_messages = []

    async for message in channel.history(limit=100):  # 必要に応じてlimitを調整
        if not message.attachments and not "```" in message.content and not message.embeds:
            if (now - message.created_at).days <= 14:
                bulk_deletable_messages.append(message)
            else:
                async_deletable_messages.append(message)

    # 一括削除
    bulk_deleted_count = 0
    if bulk_deletable_messages:
        await channel.delete_messages(bulk_deletable_messages)
        bulk_deleted_count = len(bulk_deletable_messages)

    # 個別削除
    async_deleted_count = 0
    for message in async_deletable_messages:
        await message.delete()
        async_deleted_count += 1
        await asyncio.sleep(0.5)

    total_deleted = bulk_deleted_count + async_deleted_count
    await interaction.followup.send(
        f"削除が完了しました！\n- 一括削除: {bulk_deleted_count} 件\n- 個別削除: {async_deleted_count} 件\n- 合計: {total_deleted} 件"
    )

@tree.command(name="reset_borrowed", description="借用状態を手動でリセットします（管理者専用）")
async def reset_borrowed(interaction: discord.Interaction, user_id: str):
    # このコマンドを使用するには、管理者権限が必要
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("このコマンドを使用する権限がありません。", ephemeral=True)
        return

    try:
        # 指定されたユーザーIDの借用状態をリセット
        user_id = int(user_id)  # ユーザーIDを整数に変換
        if user_id in borrowed_accounts:
            borrowed_accounts.pop(user_id)  # 借用状態を削除
            user_status.pop(user_id, None)  # ユーザーステータスも削除
            await interaction.response.send_message(f"ユーザーID {user_id} の借用状態をリセットしました。", ephemeral=True)
        else:
            await interaction.response.send_message(f"ユーザーID {user_id} は現在借用状態ではありません。", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("正しいユーザーIDを入力してください。", ephemeral=True)


# Flaskアプリケーションの設定 (ヘルスチェック用)
app = Flask(__name__)

@app.route("/health")
def health_check():
    return "OK", 200

# Discord Botを起動するスレッドとFlaskサーバーを同時に起動
from threading import Thread

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# Flask サーバーをバックグラウンドで実行
thread = Thread(target=run_flask)
thread.daemon = True
thread.start()

# Bot準備完了時のイベント
@bot.event
async def on_ready():
    await tree.sync()  # スラッシュコマンドを同期
    print(f"Logged in as {bot.user}")

# Discord Botを起動
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
