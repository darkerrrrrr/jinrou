import discord
import random, asyncio
from typing import Optional, cast
from config import get_game, RoleName, ITEM_WEIGHTS, ItemLiteral

ITEMS = {
    "📢 拡声器": "【昼用】議論中、DMのボタンを押すとBotが全体チャットで全員に静聴を呼びかけ、あなたの発言に注目を集めます。",
    "📝 遺言ノート": "【パッシブ】これを持った状態で今夜人狼に殺されると、翌朝あなたの遺言が自動公開されます。",
    "🍯 泥団子": "【投票用】今日の投票フェーズで誰かに投げつけると、相手の投票権を奪う（投票を無効化する）ことができます。",
    "🛡️ お守り": "【パッシブ】今夜人狼に襲撃されても、1度だけ自動で生き残る（身代わりアイテム）。",
    "🧪 疑惑の劇薬": "【投票用】今日の自分の投票が自動的に「2票分」としてカウントされます。",
    "🪞 姿写しの鏡": "【昼用】生存者1人を指定し、その人が昨日アイテムを引いた（普通の村人だった）かどうかを覗き見ます。",
    "🤐 沈黙の御札": "【投票用】投票フェーズで指定した1人を、次の日の議論フェーズで発言禁止（マイクミュート）にします。",
    "目隠し": "【ハズレ】引いた瞬間、全員のチャットが5秒間見えなくなります。混乱を招きます。"
}

# 📝 遺言ノートを記入するためのModal
class WillNoteModal(discord.ui.Modal):
    content = discord.ui.TextInput(
        label="遺言内容",
        style=discord.TextStyle.paragraph,
        placeholder="自分が死んだあとに公開されるメッセージを入力してください...",
        required=True,
        max_length=500
    )

    def __init__(self, guild_id: int):
        super().__init__(title="遺言ノートの記入")
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.client.get_guild(self.guild_id)
        game = get_game(self.guild_id)
        game.player_items[interaction.user.id] = "📝 遺言ノート"
        game.will_notes[interaction.user.id] = self.content.value
        if guild: await game.save_state(guild) # 保存
        await interaction.response.send_message(embed=discord.Embed(description="✅ 遺言を書き残しました。人狼に殺害された場合のみ公開されます。", color=discord.Color.green()), ephemeral=True)

# 📢 拡声器をDMから直接使うためのView
class MegaphoneUseView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="📢 拡声器を使用する", style=discord.ButtonStyle.danger)
    async def use_megaphone(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        game = get_game(self.guild_id)
        
        if game.player_items.get(user.id) != "📢 拡声器":
            return await interaction.response.send_message(embed=discord.Embed(description="❌ 使用可能な拡声器を持っていません。", color=discord.Color.red()), ephemeral=True)
        if not game.is_playing:
            return await interaction.response.send_message(embed=discord.Embed(description="⚠️ ゲーム中のみ使用可能です。", color=discord.Color.orange()), ephemeral=True)

        use_player_item(self.guild_id, user.id)
        feedback_embed = discord.Embed(description="📢 **拡声器を使用しました！**\n全体チャンネルにアナウンスを送信しました。", color=discord.Color.red())
        await interaction.response.edit_message(embed=feedback_embed, view=None)

        if hasattr(game, 'text_channel') and game.text_channel:
            embed = discord.Embed(
                title="🚨 拡声器発動！",
                description=f"📣 **{user.mention} さんが注目を求めています！**\n\n「全員静かに！私の話を聞いてください！」\n\n議論の手を止め、彼の言葉に耳を傾けましょう。",
                color=discord.Color.red()
            )
            await game.text_channel.send(embed=embed)

# 🪞 姿写しの鏡をDMから直接使うためのViewとSelect
class MirrorSelect(discord.ui.Select):
    def __init__(self, actor: discord.Member, guild_id: int):
        # 自分以外の生存者を選択肢にする
        self.guild_id = guild_id
        game = get_game(guild_id)
        current_options = [
            discord.SelectOption(label=p.display_name, value=str(p.id)) 
            for p in game.alive_players if p != actor
        ]
        super().__init__(placeholder="覗き見るプレイヤーを選択...", options=current_options)

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        game = get_game(self.guild_id)
        guild = interaction.client.get_guild(self.guild_id)
        if game.player_items.get(user.id) != "🪞 姿写しの鏡":
            return await interaction.response.send_message(embed=discord.Embed(description="❌ 使用可能な鏡を持っていません。", color=discord.Color.red()), ephemeral=True)

        target_id = int(self.values[0])
        target_member = guild.get_member(target_id) if guild else None
        if target_member is None:
            return await interaction.response.send_message(embed=discord.Embed(description="❌ 対象のプレイヤーが見つかりません。", color=discord.Color.red()), ephemeral=True)

        # ターゲットが現在も生存しているかチェック
        if target_member not in game.alive_players:
            return await interaction.response.send_message(embed=discord.Embed(description="⚠️ そのプレイヤーは既に生存していないため、覗き見ることはできません。", color=discord.Color.orange()), ephemeral=True)

        use_player_item(self.guild_id, user.id)
        target_role = game.roles.get(target_member)
        
        if target_role and target_role.name == RoleName.VILLAGER:
            res_embed = discord.Embed(title="🪞 鏡の魔力", description=f"🟢 {target_member.display_name} さんは昨夜、村人の身支度を行っていました。\n(役職を持たない村人である可能性が極めて高いです)", color=discord.Color.green())
        else:
            res_embed = discord.Embed(title="🪞 鏡の魔力", description=f"🔴 {target_member.display_name} さんは昨夜、身支度を行っていません。\n(人狼や占い師などの役職持ちである可能性があります)", color=discord.Color.red())

        await interaction.response.edit_message(embed=res_embed, view=None)

class MirrorUseView(discord.ui.View):
    def __init__(self, actor: discord.Member, guild_id: int):
        super().__init__(timeout=300)  # 昼フェーズ中に使用するため、5分のタイムアウト
        # 生存者リストをSelectメニューに引き渡す
        self.add_item(MirrorSelect(actor, guild_id))


# 🎲 夜フェーズで村人がアイテムを引くためのガチャView
class ItemDrawView(discord.ui.View):
    def __init__(self, guild_id: int, timeout=60):
        super().__init__(timeout=timeout)
        self.guild_id = guild_id

    @discord.ui.button(label="🎲 持ち物を整理する (アイテムを引く)", style=discord.ButtonStyle.primary)
    async def draw_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        game = get_game(self.guild_id)
        guild = interaction.client.get_guild(self.guild_id)
        
        if user.id in game.player_items:
            return await interaction.response.send_message(embed=discord.Embed(description="⚠️ 今夜の準備はすでに完了しています。", color=discord.Color.orange()), ephemeral=True)
        
        # ボタン無効化で二重取得を防止
        button.disabled = True
        
        # 重み付けに基づいたアイテム抽選
        item_list = list(ITEM_WEIGHTS.keys())
        item_name = cast(ItemLiteral, random.choices(item_list, weights=[ITEM_WEIGHTS[i] for i in item_list], k=1)[0])
        game.player_items[user.id] = item_name
        if guild: await game.save_state(guild) # アイテム確定時に保存
        game.check_night_actions_complete()
        
        res_embed = discord.Embed(title="🎒 アイテム支給", color=discord.Color.gold())
        res_embed.description = f"手に入れたもの: **{item_name}**\n効果: {ITEMS[item_name]}"

        if item_name == "📢 拡声器":
            res_embed.description += "\n\n👇 **昼の議論中、発言権が欲しいタイミングで下のボタンを押してください！**"
            await interaction.response.edit_message(embed=res_embed, view=MegaphoneUseView(self.guild_id))
        elif item_name == "🪞 姿写しの鏡":
            res_embed.description += "\n\n👇 **昼の議論中、怪しいと思った人を1人選んで正体を覗き見てください！**"
            await interaction.response.edit_message(embed=res_embed, view=MirrorUseView(user, self.guild_id))
        elif item_name == "📝 遺言ノート":
            await interaction.response.send_modal(WillNoteModal(self.guild_id))
        elif item_name == "🛡️ お守り":
            res_embed.description += "\n\n💡 このアイテムは朝フェーズで自動的に効果が発動します。"
            await interaction.response.edit_message(embed=res_embed, view=None)
        elif item_name in ["🍯 泥団子", "🤐 沈黙の御札", "🧪 疑惑の劇薬"]:
            res_embed.description += "\n\n💡 このアイテムは投票フェーズで使用できます。投票時に『使う』を選んでください。"
            await interaction.response.edit_message(embed=res_embed, view=None)
        elif item_name == "目隠し":
            res_embed.description += "\n\n💡 引いた瞬間、全員のチャットが5秒間見えなくなります！"
            await interaction.response.edit_message(embed=res_embed, view=None)

            # 目隠し効果の適用
            if game.progress_channel:
                try:
                    # 先にアナウンス（隠れる前に見せる）
                    blind_notice = discord.Embed(title="🙈 目隠し発動！", description="不運な誰かがハズレを引きました。\n**5秒間、参加者全員の視界を奪います！**", color=discord.Color.dark_grey())
                    await game.progress_channel.send(embed=blind_notice)
                    await asyncio.sleep(1) # 読む猶予

                    # 参加者全員の権限を個別に操作して確実に隠す
                    # (Discordの仕様上、ロール権限より個人設定が優先されるため)
                    backup_overwrites = {}
                    hide_tasks = []
                    for p in game.players:
                        backup_overwrites[p] = game.progress_channel.overwrites_for(p)
                        hide_tasks.append(game.progress_channel.set_permissions(p, view_channel=False))
                    
                    await asyncio.gather(*hide_tasks)
                    
                    await asyncio.sleep(5) # 5秒間待機
                    
                    # 元の権限設定に戻す
                    restore_tasks = [game.progress_channel.set_permissions(p, overwrite=ov) for p, ov in backup_overwrites.items()]
                    await asyncio.gather(*restore_tasks)
                except Exception as e:
                    print(f"⚠️ 目隠し効果適用失敗: {e}")
        else:
            res_embed.description += "\n\n大切にしまっておいてください。"
            await interaction.response.edit_message(embed=res_embed, view=None)

async def send_item_notification(player: discord.Member, item_name: ItemLiteral, guild_id: int):
    """プレイヤーにアイテム獲得/所持の通知と、必要なら操作ボタンを送信する"""
    embed = discord.Embed(title="🎒 アイテム所持確認", color=discord.Color.gold())
    embed.description = f"現在、あなたは **{item_name}** を持っています。\n効果: {ITEMS.get(item_name, 'なし')}"
    
    view = None
    if item_name == "📢 拡声器":
        view = MegaphoneUseView(guild_id)
    elif item_name == "🪞 姿写しの鏡":
        view = MirrorUseView(player, guild_id)
    
    try:
        await player.send(embed=embed, view=view, silent=True)
    except:
        pass


# 📦 議論中の「早い者勝ち」アイテムドロップ用View
class QuickItemView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=30)
        self.guild_id = guild_id
        self.taken: bool = False

    @discord.ui.button(label="📦 荷物を受け取る！", style=discord.ButtonStyle.success)
    async def take_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.taken: return
        
        game = get_game(self.guild_id)
        if interaction.user not in game.alive_players:
            return await interaction.response.send_message(embed=discord.Embed(description="👻 幽霊は荷物を受け取れません...", color=discord.Color.dark_grey()), ephemeral=True)

        self.taken = True
        self.stop()
        
        # 重み付けに基づいたアイテム抽選
        item_list = list(ITEM_WEIGHTS.keys())
        item_name = cast(ItemLiteral, random.choices(item_list, weights=[ITEM_WEIGHTS[i] for i in item_list], k=1)[0])
        game.player_items[interaction.user.id] = item_name
        
        embed = discord.Embed(title="🎁 荷物の中身", description=f"{interaction.user.mention} さんが一番早く荷物を受け取りました！\n中身は **{item_name}** でした！", color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=None)

def reset_items(guild_id: int) -> None:
    """全プレイヤーのアイテムをリセットする"""
    game = get_game(guild_id)
    game.player_items.clear()

def get_player_item(guild_id: int, player_id: int) -> Optional[str]:
    """
    プレイヤーの所持アイテムを取得する
    
    Args:
        player_id: プレイヤーのDiscordユーザーID
        
    Returns:
        アイテム名、持っていない場合はNone
    """
    game = get_game(guild_id)
    return game.player_items.get(player_id, None)

def use_player_item(guild_id: int, player_id: int) -> None:
    """
    プレイヤーのアイテムを使用（削除）する
    
    Args:
        player_id: プレイヤーのDiscordユーザーID
    """
    game = get_game(guild_id)
    if player_id in game.player_items:
        del game.player_items[player_id]

# 💡 main.pyで拡張機能としてエラーなく読み込ませるための必須関数（中身は空でOK）
async def setup(bot):
    pass
