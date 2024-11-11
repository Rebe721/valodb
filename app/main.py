import discord
from discord.ext import commands
import sqlite3
import os
import asyncio
from keep_alive import keep_alive

# Botの設定
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# データベースファイルの絶対パスを取得
db_path = os.path.join(os.path.dirname(__file__), 'accounts.db')

# データベースの初期化関数
def init_db():
    if not os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            name TEXT,
            id TEXT,
            password TEXT,
            rank TEXT,
            status TEXT,
            borrower TEXT
        )
        ''')
        conn.commit()
        conn.close()

# アカウントを借りたユーザーが新たにアカウントを借りられないようにするチェック
def can_borrow_account(user_id):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT borrower FROM accounts WHERE borrower=?", (user_id,))
    borrowed_accounts = c.fetchall()
    conn.close()
    return len(borrowed_accounts) == 0

# プルダウンメニューを含むView
class AccountSelectView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)

        if not can_borrow_account(user_id):
            self.add_item(discord.ui.Button(label="すでにアカウントを借りています。", disabled=True))
            return

        # データベースから利用可能なアカウントを取得し、プルダウンメニューとして設定
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT name, rank FROM accounts WHERE status='available'")
        available_accounts = c.fetchall()
        conn.close()

        sorted_accounts = sorted(available_accounts, key=lambda account: (account[0][0].lower(), int(''.join(filter(str.isdigit, account[0])) or 0)), reverse=True)

        if not sorted_accounts:
            self.add_item(discord.ui.Button(label="利用可能なアカウントはありません。", disabled=True))
        else:
            unique_names = set()
            options = []

            for account in sorted_accounts:
                name = account[0]
                if name not in unique_names:
                    options.append(discord.SelectOption(label=f"{name} - {account[1]}", value=name))
                    unique_names.add(name)

            self.account_selection = discord.ui.Select(
                placeholder="利用するアカウントを選んでください",
                options=options
            )
            self.account_selection.callback = self.on_select_account
            self.add_item(self.account_selection)

    async def on_select_account(self, interaction: discord.Interaction):
        selected_account_name = self.account_selection.values[0]

        # データベースから選択されたアカウントの詳細情報を取得
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT name, id, password, rank FROM accounts WHERE name=?", (selected_account_name,))
        account_details = c.fetchone()

        c.execute("UPDATE accounts SET status='borrowed', borrower=? WHERE name=?", (interaction.user.id, selected_account_name))
        conn.commit()
        conn.close()

        if account_details:
            await interaction.response.send_message(
                f"選択されたアカウントの詳細:\n"
                f"**名前**: {account_details[0]}\n"
                f"**ID**: {account_details[1]}\n"
                f"**パスワード**: {account_details[2]}\n"
                f"**ランク**: {account_details[3]}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("アカウント情報の取得に失敗しました。", ephemeral=True)

# アカウント利用コマンド
@bot.tree.command(name="use_account")
async def use_account(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    if not can_borrow_account(user_id):
        await interaction.response.send_message("既にアカウントを借りています。返却してください。", ephemeral=True)
    else:
        # 即時応答を確保し、非同期でビューを表示
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("利用するアカウントを選んでください:", view=AccountSelectView(user_id), ephemeral=True)

# ヘルプコマンド
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
    await interaction.response.defer(ephemeral=True)
    await interaction.followup.send(help_message, ephemeral=True)

# データベース初期化
init_db()

# Replitのサーバーを保持する
keep_alive()

# Botを実行
bot.run(os.environ['TOKEN'])

