import discord
from config import game

# ─── 時間設定モーダル ───
class TimeSettingModal(discord.ui.Modal, title='ゲーム時間の設定'):
    discussion_input = discord.ui.TextInput(label='昼の議論時間 (秒)', default='180', max_length=4)
    night_input = discord.ui.TextInput(label='夜の行動時間 (秒)', default='60', max_length=4)
    morning_input = discord.ui.TextInput(label='朝の結果発表時間 (秒)', default='15', max_length=4)

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            game.discussion_time = int(self.discussion_input.value)
            game.night_time = int(self.night_input.value)
            game.morning_time = int(self.morning_input.value)
            
            # メインの募集パネルを更新
            if game.recruit_message:
                await game.recruit_message.edit(embed=self.parent_view.create_recruit_embed(), view=self.parent_view)
            
            # 設定メニューは閉じるか、更新メッセージを表示
            await interaction.response.send_message("時間を更新しました。", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("半角数字で入力してください。", ephemeral=True)

# ─── 役職設定関連 ───
class RoleCountSelect(discord.ui.Select):
    def __init__(self, selected_role):
        self.selected_role = selected_role
        current = game.role_settings[selected_role]
        limited = ["シリアルキラー", "怪盗", "占い師", "狩人", "狂人", "霊媒師"]
        limit = 2 if selected_role in limited else 4
        options = [discord.SelectOption(label=f"{i}枚", value=str(i), default=(current == i)) for i in range(limit)]
        super().__init__(placeholder=f"【{selected_role}】の枚数を選択", options=options)

    async def callback(self, interaction: discord.Interaction):
        game.role_settings[self.selected_role] = int(self.values[0])
        
        # 1. メインの募集パネルを更新（viewを再生成してリセット）
        if game.recruit_message:
            await game.recruit_message.edit(embed=RecruitView().create_recruit_embed(), view=RecruitView())
        
        # 2. 設定メニュー（ephemeral）を更新
        await interaction.response.edit_message(content=f"【{self.selected_role}】を{self.values[0]}枚に設定しました。続けて設定できます。", view=RoleSettingView())

class RoleSelectMenu(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=f"{r} ({game.role_settings[r]}枚)", value=r) for r in game.role_settings.keys()]
        super().__init__(placeholder="変更したい役職を選択...", options=options)
    async def callback(self, interaction: discord.Interaction):
        v = discord.ui.View()
        v.add_item(RoleCountSelect(self.values[0]))
        await interaction.response.edit_message(content=f"【{self.values[0]}】の枚数を選択:", view=v)

class RoleSettingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(RoleSelectMenu())
        close_btn = discord.ui.Button(label="設定完了", style=discord.ButtonStyle.secondary)
        async def close_callback(interaction):
            # 設定画面を削除（非表示に）する
            await interaction.response.edit_message(content="設定を完了しました。", view=None)
        close_btn.callback = close_callback
        self.add_item(close_btn)

# ─── 募集・全体設定パネル ───
class RecruitView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    def create_recruit_embed(self):
        roles_text = "\n".join([f"・{k}: {v}枚" for k, v in game.role_settings.items() if v > 0])
        embed = discord.Embed(title="🐺 人狼ゲーム 参加者募集中！", color=discord.Color.dark_red())
        embed.add_field(name="👥 配役構成", value=roles_text if roles_text else "未設定")
        embed.add_field(name=f"🎮 参加者 ({len(game.players)}人)", value="\n".join([p.mention for p in game.players]) if game.players else "誰も参加していません。")
        return embed

    @discord.ui.button(label="参加", style=discord.ButtonStyle.green, custom_id="join_btn")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user not in game.players:
            game.players.append(interaction.user)
            await interaction.response.edit_message(embed=self.create_recruit_embed(), view=self)

    @discord.ui.button(label="辞退", style=discord.ButtonStyle.red, custom_id="leave_btn")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in game.players:
            game.players.remove(interaction.user)
            await interaction.response.edit_message(embed=self.create_recruit_embed(), view=self)

    @discord.ui.button(label="⏱️ 時間設定", style=discord.ButtonStyle.secondary, custom_id="settings_btn")
    async def settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TimeSettingModal(parent_view=self))

    @discord.ui.button(label="👥 役職設定", style=discord.ButtonStyle.primary, custom_id="roles_btn")
    async def role_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("役職変更:", view=RoleSettingView(), ephemeral=True)
