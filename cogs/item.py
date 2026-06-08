import discord
import random
from typing import Optional
from config import game, RoleName

ITEMS = {
    "📢 拡声器": "【昼用】議論中、DMのボタンを押すとBotが全体チャットで全員に静聴を呼びかけ、あなたの発言に注目を集めます。",
    "📝 遺言ノート": "【パッシブ】これを持った状態で今夜人狼に殺されると、翌朝あなたの遺言が自動公開されます。",
    "🍯 泥団子": "【投票用】今日の投票フェーズで誰かに投げつけると、相手の投票権を奪う（投票を無効化する）ことができます。",
    "🛡️ お守り": "【パッシブ】今夜人狼に襲撃されても、1度だけ自動で生き残る（身代わりアイテム）。",
    "🧪 疑惑の劇薬": "【投票用】今日の自分の投票が自動的に「2票分」としてカウントされます。",
    "🪞 姿写しの鏡": "【昼用】生存者1人を指定し、その人が昨日アイテムを引いた（普通の村人だった）かどうかを覗き見ます。",
    "🤐 沈黙の御札": "【投票用】投票フェーズで指定した1人を、次の日の昼の議論フェーズで完全ミュート（発言禁止）にします。"
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
    def __init__(self):
        super().__init__(title="遺言ノートの記入")
    async def on_submit(self, interaction: discord.Interaction):
        game.player_items[interaction.user.id] = "📝 遺言ノート"
        game.will_notes[interaction.user.id] = self.content.value
        await interaction.response.send_message("✅ 遺言を書き残しました。人狼に殺害された場合のみ公開されます。", ephemeral=True)

# 📢 拡声器をDMから直接使うためのView
class MegaphoneUseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📢 拡声器を使用する", style=discord.ButtonStyle.danger)
    async def use_megaphone(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        
        if game.player_items.get(user.id) != "📢 拡声器":
            return await interaction.response.send_message("使用可能な拡声器を持っていません。", ephemeral=True)
        if not game.is_playing:
            return await interaction.response.send_message("ゲーム中のみ使用可能です。", ephemeral=True)

        use_player_item(user.id)
        await interaction.response.edit_message(content="📢 **拡声器を使用しました！** 全体チャンネルにアナウンスを送信しました。", view=None)

        if hasattr(game, 'text_channel') and game.text_channel:
            announcement = (
                f"🚨🚨🚨 **【拡声器発動】** 🚨🚨🚨\n"
                f"📣 **{user.mention} さんが拡声器を使用しました！**\n"
                f"「全員静かに！私の話を聞いてください！」\n\n"
                f"🔮 生存者の皆さんは、一旦議論の手を止めて彼の発言に注目してください！"
            )
            await game.text_channel.send(announcement)

# 🪞 姿写しの鏡をDMから直接使うためのViewとSelect
class MirrorSelect(discord.ui.Select):
    def __init__(self, actor):
        # 自分以外の生存者を選択肢にする
        current_options = [
            discord.SelectOption(label=p.display_name, value=str(p.id)) 
            for p in game.alive_players if p != actor
        ]
        super().__init__(placeholder="覗き見るプレイヤーを選択...", options=current_options)

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        if game.player_items.get(user.id) != "🪞 姿写しの鏡":
            return await interaction.response.send_message("使用可能な鏡を持っていません。", ephemeral=True)

        target_id = int(self.values[0])
        target_member = interaction.guild.get_member(target_id) or await interaction.guild.fetch_member(target_id)
        if not target_member:
            return await interaction.response.send_message("対象のプレイヤーが見つかりません。", ephemeral=True)

        # ターゲットが現在も生存しているかチェック
        if target_member not in game.alive_players:
            return await interaction.response.send_message("そのプレイヤーは既に生存していないため、覗き見ることはできません。", ephemeral=True)

        use_player_item(user.id)
        target_role = game.roles.get(target_member)
        
        if target_role and target_role.name == RoleName.VILLAGER:
            result_text = f"🟢 【鏡の魔力】 {target_member.display_name} さんは、昨夜『村人の身支度（アイテム支給）』を行っていました。（普通の村人である可能性が極めて高いです）"
        else:
            result_text = f"🔴 【鏡の魔力】 {target_member.display_name} さんは、昨夜『村人の身支度』を行っていません。（人狼や占い師などの役職持ち、あるいはアイテムを引き忘れた人です）"

        await interaction.response.edit_message(content=result_text, view=None)

class MirrorUseView(discord.ui.View):
    def __init__(self, actor):
        super().__init__(timeout=300)  # 昼フェーズ中に使用するため、5分のタイムアウト
        # 生存者リストをSelectメニューに引き渡す
        self.add_item(MirrorSelect(actor))


# 🎲 夜フェーズで村人がアイテムを引くためのガチャView
class ItemDrawView(discord.ui.View):
    def __init__(self, timeout=60):
        super().__init__(timeout=timeout)

    @discord.ui.button(label="🎲 持ち物を整理する (アイテムを引く)", style=discord.ButtonStyle.primary)
    async def draw_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        
        if user.id in game.player_items:
            return await interaction.response.send_message("今夜の準備はすでに完了しています。", ephemeral=True)
        
        # ボタン無効化で二重取得を防止
        button.disabled = True
        
        item_name = random.choice(list(ITEMS.keys()))
        game.player_items[user.id] = item_name
        game.check_night_actions_complete()
        
        if item_name == "📢 拡声器":
            await interaction.response.edit_message(
                content=f"🎒 **アイテムを支給されました！**\n\n手に入れたもの: **{item_name}**\n効果: {ITEMS[item_name]}\n\n👇 **昼の議論中、発言権が欲しいタイミングで下のボタンを押してください！**", 
                view=MegaphoneUseView()
            )
        elif item_name == "🪞 姿写しの鏡":
            await interaction.response.edit_message(
                content=f"🎒 **アイテムを支給されました！**\n\n手に入れたもの: **{item_name}**\n効果: {ITEMS[item_name]}\n\n👇 **昼の議論中、怪しいと思った人を1人選んで正体を覗き見てください！**", 
                view=MirrorUseView(user)
            )
        elif item_name == "📝 遺言ノート":
            await interaction.response.send_modal(WillNoteModal())
        elif item_name == "🛡️ お守り":
            await interaction.response.edit_message(
                content=f"🎒 **アイテムを支給されました！**\n\n手に入れたもの: **{item_name}**\n効果: {ITEMS[item_name]}\n\n💡 このアイテムは朝フェーズで自動的に効果が発動します。今夜人狼に襲撃されても生き残ります！", 
                view=None
            )
        elif item_name in ["🍯 泥団子", "🤐 沈黙の御札", "🧪 疑惑の劇薬"]:
            await interaction.response.edit_message(
                content=f"🎒 **アイテムを支給されました！**\n\n手に入れたもの: **{item_name}**\n効果: {ITEMS[item_name]}\n\n💡 このアイテムは投票フェーズで使用できます。投票時に『使う』を選んでください。", 
                view=None
            )
        else:
            await interaction.response.edit_message(
                content=f"🎒 **アイテムを支給されました！**\n\n手に入れたもの: **{item_name}**\n効果: {ITEMS[item_name]}\n\n大切にしまっておいてください。", 
                view=None
            )

def reset_items() -> None:
    """全プレイヤーのアイテムをリセットする"""
    game.player_items.clear()

def get_player_item(player_id: int) -> Optional[str]:
    """
    プレイヤーの所持アイテムを取得する
    
    Args:
        player_id: プレイヤーのDiscordユーザーID
        
    Returns:
        アイテム名、持っていない場合はNone
    """
    return game.player_items.get(player_id, None)

def use_player_item(player_id: int) -> None:
    """
    プレイヤーのアイテムを使用（削除）する
    
    Args:
        player_id: プレイヤーのDiscordユーザーID
    """
    if player_id in game.player_items:
        del game.player_items[player_id]

# 💡 main.pyで拡張機能としてエラーなく読み込ませるための必須関数（中身は空でOK）
async def setup(bot):
    pass
