# views.py
import discord
from config import game

# ─── 時間設定モーダル ───
class TimeSettingModal(discord.ui.Modal, title='ゲーム時間の設定'):
    discussion_input = discord.ui.TextInput(label='議論の時間 (秒)', default='180', max_length=4)
    night_input = discord.ui.TextInput(label='夜の行動時間 (秒)', default='60', max_length=4)
    morning_input = discord.ui.TextInput(label='朝の結果発表時間 (秒)', default='15', max_length=4)

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view  # 募集画面のViewを記憶しておく

    async def on_submit(self, interaction: discord.Interaction):
        try:
            game.discussion_time = int(self.discussion_input.value)
            game.night_time = int(self.night_input.value)
            game.morning_time = int(self.morning_input.value)
            
            # ⏱️ 時間が変更されたので、Embed（募集画面）もその場で最新に書き換える
            await interaction.response.edit_message(
                embed=self.parent_view.create_recruit_embed(),
                view=self.parent_view
            )
        except ValueError:
            await interaction.response.send_message("エラー: 半角数字で入力してください。", ephemeral=True)

# ─── 役職個別枚数変更セレクトメニュー ───
class RoleCountSelect(discord.ui.Select):
    def __init__(self, selected_role):
        self.selected_role = selected_role
        current = game.role_settings[selected_role]
        options = [
            discord.SelectOption(label="0枚", value="0", default=(current == 0)),
            discord.SelectOption(label="1枚", value="1", default=(current == 1)),
            discord.SelectOption(label="2枚", value="2", default=(current == 2)),
            discord.SelectOption(label="3枚", value="3", default=(current == 3)),
        ]
        super().__init__(placeholder=f"【{selected_role}】の枚数を選択（現在: {current}枚）", options=options)

    async def callback(self, interaction: discord.Interaction):
        game.role_settings[self.selected_role] = int(self.values[0])
        
        current_status = "\n".join([f"・{k}: {v}枚" for k, v in game.role_settings.items() if v > 0])
        await interaction.response.edit_message(
            content=f"⚙️ 役職を変更しました。\n\n現在の役職セット内訳:\n{current_status}\n\n続けて変更する場合は対象の役職を選んでください：",
            view=RoleSettingView()
        )

class RoleSelectMenu(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=f"{role_name} ({game.role_settings[role_name]}枚)", value=role_name)
            for role_name in game.role_settings.keys()
        ]
        super().__init__(placeholder="枚数を変更したい役職を選択してください...", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_role = self.values[0]
        count_view = discord.ui.View(timeout=60)
        count_view.add_item(RoleCountSelect(selected_role))
        
        back_button = discord.ui.Button(label="🔙 役職選択に戻る", style=discord.ButtonStyle.secondary)
        async def back_callback(inter):
            current_status = "\n".join([f"・{k}: {v}枚" for k, v in game.role_settings.items() if v > 0])
            await inter.response.edit_message(
                content=f"現在の役職セット内訳:\n{current_status}\n\n変更したい役職の枚数を選択してください：",
                view=RoleSettingView()
            )
        back_button.callback = back_callback
        count_view.add_item(back_button)

        await interaction.response.edit_message(
            content=f"⚙️ **役職枚数設定: 【{selected_role}】**\n何枚セットするか選択してください。",
            view=count_view
        )

class RoleSettingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(RoleSelectMenu())


# ─── 募集・全体設定パネル ───
class RecruitView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # 🎨 募集画面の見た目（Embed）を自動で生成する関数
    def create_recruit_embed(self):
        roles_text = "\n".join([f"・{k}: {v}枚" for k, v in game.role_settings.items() if v > 0])
        if not roles_text:
            roles_text = "・（役職が設定されていません）"

        if game.players:
            players_text = "\n".join([f"{i+1}. {p.mention}" for i, p in enumerate(game.players)])
        else:
            players_text = "誰も参加していません。ボタンを押して参加しよう！"

        embed = discord.Embed(
            title="🐺 人狼ゲーム 参加者募集中！",
            description="下のボタンを押して参加・設定を行ってください。\n全員揃ったらゲームを開始します。",
            color=discord.Color.dark_red()
        )
        embed.add_field(name="⏱️ 制限時間設定", value=f"・議論時間: {game.discussion_time}秒\n・夜の行動: {game.night_time}秒\n・朝の発表: {game.morning_time}秒", inline=True)
        embed.add_field(name="👥 配役構成", value=roles_text, inline=True)
        embed.add_field(name=f"🎮 参加プレイヤー一覧 (現在 {len(game.players)}人)", value=players_text, inline=False)
        
        # ⚙️ 【修正箇所】「24時間稼働モード」を削除し、システム名のみにスッキリさせました
        embed.set_footer(text="Game Management System")
        return embed

    @discord.ui.button(label="参加", style=discord.ButtonStyle.green, custom_id="join_btn")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user not in game.players:
            game.players.append(interaction.user)
            # 参加者が増えたのでEmbedを更新
            await interaction.response.edit_message(embed=self.create_recruit_embed(), view=self)
        else:
            await interaction.response.send_message("既に参加しています。", ephemeral=True)

    @discord.ui.button(label="辞退", style=discord.ButtonStyle.red, custom_id="leave_btn")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in game.players:
            game.players.remove(interaction.user)
            # 辞退者が出たのでEmbedを更新
            await interaction.response.edit_message(embed=self.create_recruit_embed(), view=self)
        else:
            await interaction.response.send_message("参加していません。", ephemeral=True)

    @discord.ui.button(label="⏱️ 時間設定", style=discord.ButtonStyle.secondary, custom_id="settings_btn")
    async def settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 自分自身（RecruitView）をモーダルに渡して、時間変更後にEmbedを上書きできるようにする
        await interaction.response.send_modal(TimeSettingModal(parent_view=self))

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
