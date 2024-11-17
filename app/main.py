import discord
from discord.ext import commands
from discord.ui import View, Select
import gspread
import os
from dotenv import load_dotenv
from flask import Flask

# .envファイルの読み込み
load_dotenv()

# Flaskアプリの設定（Koyeb用）
app = Flask(__name__)

# Google Sheets APIとの接続設定
gc = gspread.service_account(filename=os.getenv('CREDENTIALS_JSON'))
sheet = gc.open("Accounts").sheet1  # アカウントデータのシート

# ボットの設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ボット起動時の処理
@bot.event
async def on_ready():
    print(f"{bot.user} がログインしました!")

# アカウント登録
@bot.tree.command(name="register")
async def register(interaction: discord.Interaction, name: str, account_id: str, password: str, rank: str):
    try:
        # スプレッドシートに新しいアカウントを登録
        sheet.append_row([name, account_id, password, rank, "available", ""])
        await interaction.response.send_message(f"アカウント **{name}** が正常に登録されました。", ephemeral=True)
    except discord.errors.NotFound:
        await interaction.followup.send(f"アカウント **{name}** が正常に登録されました。（応答が遅延した可能性があります）", ephemeral=True)

# アカウント返却
@bot.tree.command(name="return_account")
async def return_account(interaction: discord.Interaction, name: str, new_rank: str):
    user_id = str(interaction.user.id)
    records = sheet.get_all_records()
    for index, record in enumerate(records):
        borrower = str(record.get("borrower", ""))
        if record.get("name", "").strip() == name and borrower.strip() == user_id:
            try:
                # スプレッドシートの更新
                sheet.update_cell(index + 2, 4, new_rank)  # ランクを更新
                sheet.update_cell(index + 2, 5, "available")  # 状態を更新
                sheet.update_cell(index + 2, 6, "")  # 借り手をクリア
                await interaction.response.send_message(f"アカウント **{name}** が返却され、ランクが更新されました。", ephemeral=True)

                # 返却通知
                channel = bot.get_channel(1305414048187154474)  # 通知用チャンネルID
                if channel:
                    try:
                        await channel.send(f"ユーザー <@{user_id}> がアカウント **{name}** を返却しました！")
                    except discord.errors.Forbidden:
                        print(f"チャンネルへのアクセス権限がありません: チャンネルID {channel.id}")
                else:
                    print("通知用チャンネルが見つかりません。")

                return
            except Exception as e:
                print(f"スプレッドシートの更新中にエラー: {e}")
                await interaction.response.send_message("アカウントの返却中にエラーが発生しました。", ephemeral=True)
                return
    await interaction.response.send_message("アカウントの返却に失敗しました。指定されたアカウントを借りていない可能性があります。", ephemeral=True)

# アカウント選択
class AccountSelectView(View):
    def __init__(self, user_id: str, records: list):
        super().__init__(timeout=900.0)
        self.user_id = user_id
        self.records = records
        self.account_selection = Select(placeholder="利用するアカウントを選んでください", min_values=1, max_values=1, options=[])
        for record in records:
            self.account_selection.add_option(label=record["name"], value=record["name"])
        self.add_item(self.account_selection)

    async def on_select_account(self, interaction: discord.Interaction):
        try:
            # ユーザーが既にアカウントを借りているか確認
            for record in self.records:
                if record["borrower"] == self.user_id:
                    await interaction.response.send_message(
                        f"既にアカウント **{record['name']}** を借りています。返却してから新しいアカウントを借りてください。",
                        ephemeral=True
                    )
                    return

            # 選択されたアカウントを取得
            selected_account_name = self.account_selection.values[0]

            # 該当するアカウントを検索
            for index, record in enumerate(self.records):
                if record["name"] == selected_account_name:
                    # アカウントの状態を更新
                    sheet.update_cell(index + 2, 5, "borrowed")  # 状態を "borrowed" に
                    sheet.update_cell(index + 2, 6, self.user_id)  # 借り手を設定

                    # 応答メッセージを送信
                    await interaction.response.send_message(
                        f"アカウント **{record['name']}** の詳細:\n"
                        f"**ID**: {record['id']}\n"
                        f"**パスワード**: {record['password']}\n"
                        f"**ランク**: {record['rank']}",
                        ephemeral=True
                    )

                    # 借りた後の全体通知
                    channel = bot.get_channel(1307661467578925056)  # 通知用チャンネルID
                    if channel:
                        try:
                            await channel.send(f"ユーザー <@{self.user_id}> がアカウント **{record['name']}** を借りました！")
                        except discord.errors.Forbidden:
                            print(f"チャンネルへのアクセス権限がありません: チャンネルID {channel.id}")
                    else:
                        print("通知用チャンネルが見つかりません。")
                    return

            # アカウントが見つからない場合
            await interaction.response.send_message("選択されたアカウントが見つかりませんでした。", ephemeral=True)
        except Exception as e:
            print(f"選択処理中のエラー: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("アカウント選択中にエラーが発生しました。", ephemeral=True)

# Flaskのヘルスチェック
@app.route("/health")
def health_check():
    return "OK", 200

# ボットの起動
if __name__ == "__main__":
    bot.run(os.getenv('TOKEN'))
    app.run(host="0.0.0.0", port=8080)
