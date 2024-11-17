import discord
from discord.ext import commands
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from keep_alive import keep_alive  # Replitでサーバーを保持するためのモジュール

# Botの設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Google スプレッドシートの認証設定
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name("CREDENTIALS_JSON", scope)
gc = gspread.authorize(credentials)

# スプレッドシートを取得
sheet = gc.open("Discord_database").sheet1  # "Accounts" をスプレッドシートの名前に変更してください

# アカウントを借りたユーザーが新たにアカウントを借りられないようにするチェック
def can_borrow_account(user_id):
    records = sheet.get_all_records()
    for record in records:
        if record["Borrower"] == str(user_id):
            return False
    return True

# スラッシュコマンド: アカウント登録
@bot.tree.command(name="register")
async def register(interaction: discord.Interaction, name: str, account_id: str, password: str, rank: str):
    # スプレッドシートに新しいアカウントを登録
    sheet.append_row([name, account_id, password, rank, "available", ""])
    await interaction.response.send_message(f"アカウント **{name}** が正常に登録されました。", ephemeral=True)

# スラッシュコマンド: アカウント利用
@bot.tree.command(name="use_account")
async def use_account(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    # 既にアカウントを借りているか確認
    if not can_borrow_account(user_id):
        await interaction.response.send_message("既にアカウントを借りています。返却してください。", ephemeral=True)
        return

    # 利用可能なアカウントを取得
    records = sheet.get_all_records()
    available_accounts = [record for record in records if record["Status"] == "available"]

    if not available_accounts:
        await interaction.response.send_message("現在利用可能なアカウントがありません。", ephemeral=True)
        return

    # アカウントリストを作成して送信
    options = [
        discord.SelectOption(label=f"{record['Name']} - {record['Rank']}", value=record["Name"])
        for record in available_accounts
    ]

    class AccountSelectView(discord.ui.View):
        @discord.ui.select(placeholder="利用するアカウントを選んでください", options=options)
        async def select_account(self, select, interaction):
            selected_name = select.values[0]
            for i, record in enumerate(records):
                if record["Name"] == selected_name:
                    sheet.update_cell(i + 2, 5, "borrowed")  # Status列を更新
                    sheet.update_cell(i + 2, 6, str(user_id))  # Borrower列を更新
                    break

            # 全体通知
            await interaction.channel.send(f"**{interaction.user.name}** がアカウント **{selected_name}** を借りました！")

            await interaction.response.send_message(
                f"アカウント **{selected_name}** を借りました。詳細は以下の通りです:\n"
                f"**ID**: {record['ID']}\n"
                f"**Password**: {record['Password']}\n"
                f"**Rank**: {record['Rank']}",
                ephemeral=True
            )

    await interaction.response.send_message("利用するアカウントを選んでください:", view=AccountSelectView(), ephemeral=True)

# スラッシュコマンド: アカウント返却
@bot.tree.command(name="return_account")
async def return_account(interaction: discord.Interaction, name: str, new_rank: str):
    user_id = str(interaction.user.id)

    # 該当アカウントを検索し、借りているか確認
    records = sheet.get_all_records()
    for i, record in enumerate(records):
        if record["Name"] == name and record["Borrower"] == user_id:
            # ランクを更新し、アカウントを返却
            sheet.update_cell(i + 2, 4, new_rank)  # Rank列を更新
            sheet.update_cell(i + 2, 5, "available")  # Status列を更新
            sheet.update_cell(i + 2, 6, "")  # Borrower列を空に
            await interaction.response.send_message(f"アカウント **{name}** を返却しました。ランクは **{new_rank}** に更新されました。", ephemeral=True)
            return

    await interaction.response.send_message("指定されたアカウントを借りていないか、名前が間違っています。", ephemeral=True)

# スラッシュコマンド: ヘルプ
@bot.tree.command(name="helplist")
async def helplist(interaction: discord.Interaction):
    help_message = """
    **利用可能なコマンド:**

    **/register <名前> <ID> <パスワード> <ランク>**  
    アカウントを登録します。

    **/use_account**  
    利用可能なアカウントから選択して使用します。

    **/return_account <名前> <新しいランク>**  
    使用中のアカウントを返却し、ランクを更新します。
    """
    await interaction.response.send_message(help_message, ephemeral=True)

# Replitのサーバーを保持
keep_alive()

# Botを実行
try:
    bot.run(os.environ['TOKEN'])
except Exception as e:
    print(f"エラーが発生しました: {e}")
    os.system("kill 1")
