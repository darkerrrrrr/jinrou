# views.py
import discord
from config import game

# ─── 時間設定モーダル ───
class TimeSettingModal(discord.ui.Modal, title='ゲーム時間の設定'):
    discussion_input = discord.ui.TextInput(label='議論の時間 (秒)', default='180', max_length=4)
    night_input = discord.ui.TextInput(label='夜の行動時間 (秒)', default='60', max_length=4)
    morning_input = discord.ui.TextInput(label='朝の結果発表時間 (秒)', default='15', max_length=4)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            game.discussion_time = int(self.discussion_input.value)
            game.night_time = int(self.night_input.value)
            game.morning_time = int(self.morning_input.value)
            await interaction.response.send_message(
                f"⏱️ 時間設定完了 - 議論: {game.discussion_time}秒 / 夜: {game.night_time}秒 / 朝: {game.morning_time}秒"
            )
        except ValueError:
            await interaction.response.send_message("エラー: 半角数字で入力してください。", ephemeral=True)

# ─── 役職個別枚数変更セレクトメニュー ───
class RoleCountSelect(discord.ui.Select):
    def __init__(self, role_name):
        self.role_name = role_name
        current = game.role_settings[role_name]
        options = [
            discord.SelectOption(label="0枚", value="0", default=(current == 0)),
            discord.SelectOption(label="1枚", value="1", default=(current == 1)),
            discord.SelectOption(label="2枚", value="2", default=(current == 2)),
            discord.SelectOption(label="3枚", value="3", default=(current == 3)),
        ]
        super().__init__(placeholder=f"{role_name} の枚数を選択 (現在: {current}枚)", options=options)

    async def callback(self, interaction: discord.Interaction):
        count = int(self.values[0])
        game.role_settings[self.role_name] = count
        await interaction.response.send_message(f"👥 【{self.role_name}】を {count} 枚に設定しました。", ephemeral=True)

class RoleSettingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        for role_name in game.role_settings.keys():
            self.add_item(RoleCountSelect(role_name))

# ─── 募集・全体設定パネル ───
class RecruitView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="参加", style=discord.ButtonStyle.green, custom_id="join_btn")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user not in game.players:
            game.players.append(interaction.user)
            await interaction.response.send_message(f"{interaction.user.display_name}さんが参加しました。(現在 {len(game.players)}人)")
        else:
            await interaction.response.send_message("既に参加しています。", ephemeral=True)

    @discord.ui.button(label="辞退", style=discord.ButtonStyle.red, custom_id="leave_btn")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in game.players:
            game.players.remove(interaction.user)
            await interaction.response.send_message(f"{interaction.user.display_name}さんが辞退しました。(現在 {len(game.players)}人)")
        else:
            await interaction.response.send_message("参加していません。", ephemeral=True)

    @discord.ui.button(label="⏱️ 時間設定", style=discord.ButtonStyle.secondary, custom_id="settings_btn")
    async def settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TimeSettingModal())

    @discord.ui.button(label="👥 役職設定", style=discord.ButtonStyle.primary, custom_id="roles_btn")
    async def role_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_status = "\n".join([f"・{k}: {v}枚" for k, v in game.role_settings.items() if v > 0])
        await interaction.response.send_message(
            f"現在の役職セット内訳:\n{current_status}\n\n変更したい役職の枚数を選択してください：",
            view=RoleSettingView(),
            ephemeral=True
        )

# ─── 一般役職アクション用セレクトメニュー ───
class RoleActionSelect(discord.ui.Select):
    def __init__(self, actor, targets, placeholder, action_type):
        self.actor = actor
        self.action_type = action_type
        options = [discord.SelectOption(label=p.display_name, value=str(p.id)) for p in targets]
        super().__init__(placeholder=placeholder, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        target_id = int(self.values[0])
        target = interaction.client.get_user(target_id)
        
        game.actions[self.actor] = target
        
        if self.action_type == "fortune":
            target_role_name = game.roles[target].name
            result = "人狼" if target_role_name == "人狼" else "人間"
            await interaction.followup.send(f"🔮 占い結果: {target.display_name}さんは【{result}】陣営です。", ephemeral=True)
        else:
            await interaction.followup.send(f"選択を完了しました。（対象: {target.display_name}）", ephemeral=True)

class RoleActionView(discord.ui.View):
    def __init__(self, actor, targets, placeholder="対象を選択してください", action_type="default"):
        super().__init__(timeout=60)
        self.add_item(RoleActionSelect(actor, targets, placeholder, action_type))

# ─── 怪盗専用即時確定セレクトメニュー ───
class ThiefSelect(discord.ui.Select):
    def __init__(self, targets):
        options = [discord.SelectOption(label=p.display_name, value=str(p.id)) for p in targets]
        super().__init__(placeholder="役職を盗む相手を選んでください...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        target_id = int(self.values[0])
        target = interaction.client.get_user(target_id)
        
        thief_obj = game.roles[interaction.user]
        target_obj = game.roles[target]
        
        # 1日目の夜、選んだ瞬間に内部データを即時入れ替える
        thief_obj.team = target_obj.team
        target_obj.player = interaction.user
        thief_obj.player = target
        
        game.roles[interaction.user] = target_obj
        game.roles[target] = thief_obj
        
        await interaction.followup.send(
            f"🕵️【怪盗の即時報告】\n{target.display_name}さんの役職を盗みました。\n"
            f"あなたの新しい真の役職: 【{target_obj.name}】（{target_obj.team}陣営）",
            ephemeral=True
        )
        game.thief_action_done = True

class ThiefView(discord.ui.View):
    def __init__(self, targets):
        super().__init__(timeout=60)
        self.add_item(ThiefSelect(targets))