from discord.ext import commands
import sqlite3
import os
import asyncio
from keep_alive import keep_alive
from keep_alive import keep_alive  # keep_alive.pyをインポート

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
    conn = sqlite3.connect('accounts.db')
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
# Botが準備完了したときのイベント
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f"スラッシュコマンドが {len(synced)} 個同期されました。")
    except Exception as e:
        print(f"同期中にエラーが発生しました: {e}")

# アカウントを借りたユーザーが新たにアカウントを借りられないようにするチェック
def can_borrow_account(user_id):
    conn = sqlite3.connect(db_path)
    conn = sqlite3.connect('accounts.db')
    c = conn.cursor()
    c.execute("SELECT borrower FROM accounts WHERE borrower=?", (user_id,))
    borrowed_accounts = c.fetchall()
@@ -46,51 +50,44 @@ class AccountSelectView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)

        # アカウントを借りている場合、メニューを表示せず通知を出す
        if not can_borrow_account(user_id):
            self.add_item(discord.ui.Button(label="すでにアカウントを借りています。", disabled=True))
            return

        # データベースから利用可能なアカウントを取得し、プルダウンメニューとして設定
        conn = sqlite3.connect(db_path)
        conn = sqlite3.connect('accounts.db')
        c = conn.cursor()
        c.execute("SELECT name, rank FROM accounts WHERE status='available'")
        available_accounts = c.fetchall()
        conn.close()

        # 名前の順序を指定通りに並べる（英字の後に続く数字でソート）
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
        # プルダウンメニューの設定
        self.account_selection = discord.ui.Select(
            placeholder="利用するアカウントを選んでください",
            options=[discord.SelectOption(label=f"{account[0]} - {account[1]}", value=account[0]) for account in sorted_accounts]
        )
        self.account_selection.callback = self.on_select_account
        self.add_item(self.account_selection)

    async def on_select_account(self, interaction: discord.Interaction):
        selected_account_name = self.account_selection.values[0]

        # データベースから選択されたアカウントの詳細情報を取得
        conn = sqlite3.connect(db_path)
        conn = sqlite3.connect('accounts.db')
        c = conn.cursor()
        c.execute("SELECT name, id, password, rank FROM accounts WHERE name=?", (selected_account_name,))
        account_details = c.fetchone()

        # 選択されたアカウントを借りたユーザーとして更新
        c.execute("UPDATE accounts SET status='borrowed', borrower=? WHERE name=?", (interaction.user.id, selected_account_name))
        conn.commit()
        conn.close()

        # 選択されたアカウントの詳細情報を返す
        if account_details:
            await interaction.response.send_message(
                f"選択されたアカウントの詳細:\n"
@@ -103,19 +100,53 @@ async def on_select_account(self, interaction: discord.Interaction):
        else:
            await interaction.response.send_message("アカウント情報の取得に失敗しました。", ephemeral=True)

# アカウント利用コマンド
# アカウントを登録するコマンド
@bot.tree.command(name="register")
async def register(interaction: discord.Interaction, name: str, account_id: str, password: str, rank: str):
    # データベースに新しいアカウントを追加
    conn = sqlite3.connect('accounts.db')
    c = conn.cursor()
    c.execute("INSERT INTO accounts (name, id, password, rank, status, borrower) VALUES (?, ?, ?, ?, 'available', '')", 
              (name, account_id, password, rank))
    conn.commit()
    conn.close()
    # ephemeralをTrueに設定して本人にのみ通知
    await interaction.response.send_message(f"アカウント **{name}** が正常に登録されました。", ephemeral=True)
# アカウントを返却するコマンド
@bot.tree.command(name="return_account")
async def return_account(interaction: discord.Interaction, name: str, new_rank: str):
    user_id = str(interaction.user.id)
    # データベースで該当アカウントを確認し、借りたアカウントであるかをチェック
    conn = sqlite3.connect('accounts.db')
    c = conn.cursor()
    c.execute("SELECT borrower FROM accounts WHERE name=? AND borrower=?", (name, user_id))
    account = c.fetchone()
    if account:
        # アカウントのランクを更新し、状態を利用可能に設定
        c.execute("UPDATE accounts SET rank=?, status='available', borrower='' WHERE name=?", (new_rank, name))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"アカウント **{name}** が返却され、ランクが更新されました。", ephemeral=True)
    else:
        conn.close()
        await interaction.response.send_message("アカウントの返却に失敗しました。指定されたアカウントを借りていない可能性があります。", ephemeral=True)
# スラッシュコマンド: アカウント利用
@bot.tree.command(name="use_account")
async def use_account(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    # アカウントを既に借りているかどうかをチェック
    if not can_borrow_account(user_id):
        await interaction.response.send_message("既にアカウントを借りています。返却してください。", ephemeral=True)
    else:
        # 即時応答を確保し、非同期でビューを表示
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("利用するアカウントを選んでください:", view=AccountSelectView(user_id), ephemeral=True)
        await interaction.response.send_message("利用するアカウントを選んでください:", view=AccountSelectView(user_id), ephemeral=True)

# ヘルプコマンド
# スラッシュコマンド: ヘルプ
@bot.tree.command(name="helplist")
async def helplist(interaction: discord.Interaction):
    help_message = """
@@ -130,15 +161,18 @@ async def helplist(interaction: discord.Interaction):
    **/return_account <名前> <新しいランク>**  
    使用中のアカウントを返却し、ランクを更新します。
    """
    await interaction.response.defer(ephemeral=True)
    await interaction.followup.send(help_message, ephemeral=True)
    await interaction.response.send_message(help_message, ephemeral=True)

# データベース初期化
init_db()

# Replitのサーバーを保持する
keep_alive()

# Botを実行
bot.run(os.environ['TOKEN'])
# Botを実行（トークンを環境変数から取得）
try:
    bot.run(os.environ['TOKEN'])  # 環境変数からボットのトークンを取得
except Exception as e:
    print(f"エラーが発生しました: {e}")
    os.system("kill 1")  # ボットが停止する場合、Replit環境を終了させる
