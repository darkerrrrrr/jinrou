import discord
import random
from config import game

player_items = {}
silenced_players = set()

ITEMS = {
    "📢 拡声器": "【昼用】議論中、DMのボタンを押すとBotが全体チャットで全員に静聴を呼びかけ、あなたの発言に注目を集めます。",
    "📝 遺言ノート": "【パッシブ】これを持った状態で今夜人狼に殺されると、翌朝あなたの遺言が自動公開されます。",
    "🍯 泥団子": "【投票用】今日の投票フェーズで誰かに投げつけると、相手の投票権を奪う（投票を無効化する）ことができます。",
    "🛡️ お守り": "【パッシブ】今夜人狼に襲撃されても、1度だけ自動で生き残る（身代わりアイテム）。",
    "🧪 疑惑の劇薬": "【投票用】今日の自分の投票が自動的に「2票分」としてカウントされます。",
    "🪞 姿写しの鏡": "【昼用】生存者1人を指定し、その人が昨日アイテムを引いた（普通の村人だった）かどうかを覗き見ます。",
    "🤐 沈黙の御札": "【投票用】投票フェーズで指定した1人を、次の日の昼の議論フェーズで完全ミュート（発言禁止）にします。"
}

class MegaphoneUseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📢 拡声器を使用する", style=discord.ButtonStyle.danger)
    async def use_megaphone(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if player_items.get(user.id) != "📢 拡声器":
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

class MirrorSelect(discord.ui.Select):
    def __init__(self, alive_players):
        # 💡 起動時ではなく、アイテムが配られた時点の生存者リストを受け取って選択肢を作る
        options = [discord.SelectOption(label=p.display_name, value=str(p.id)) for p in alive_players]
        super().__init__(placeholder="覗き見るプレイヤーを選択...", options=options)

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        if player_items.get(user.id) != "🪞 姿写しの鏡":
            return await interaction.response.send_message("使用可能な鏡を持っていません。", ephemeral=True)

        target_id = int(self.values[0])
        target_member = interaction.guild.get_member(target_id)
        if not target_member:
            return await interaction.response.send_message("対象のプレイヤーが見つかりません。", ephemeral=True)

        use_player_item(user.id)
        target_role = game.roles.get(target_member)
        
        if target_role and target_role.name == "村人":
            result_text = f"🟢 【鏡の魔力】 {target_member.display_name} さんは、昨夜『村人の身支度（アイテム支給）』を行っていました。（普通の村人である可能性が極めて高いです）"
        else:
            result_text = f"🔴 【鏡の魔力】 {target_member.display_name} さんは、昨夜『村人の身支度』を行っていません。（人狼や占い師などの役職持ち、あるいはアイテムを引き忘れた人です）"

        await interaction.response.edit_message(content=result_text, view=None)

class MirrorUseView(discord.ui.View):
    def __init__(self, alive_players):
        super().__init__(timeout=None)
        # 生存者リストをSelectに引き渡す
        self.add_item(MirrorSelect(alive_players))

class ItemDrawView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="🎲 持ち物を整理する (アイテムを引く)", style=discord.ButtonStyle.primary)
    async def draw_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if user.id in player_items:
            return await interaction.response.send_message("今夜の準備はすでに完了しています。", ephemeral=True)
        
        item_name = random.choice(list(ITEMS.keys()))
        player_items[user.id] = item_name
        
        if item_name == "📢 拡声器":
            await interaction.response.edit_message(
                content=f"🎒 **アイテムを支給されました！**\n\n手に入れたもの: **{item_name}**\n効果: {ITEMS[item_name]}\n\n👇 **昼の議論中、発言権が欲しいタイミングで下のボタンを押してください！**", 
                view=MegaphoneUseView()
            )
        elif item_name == "🪞 姿写しの鏡":
            # 💡 現在のゲームの生存者リストをViewに渡してボタンを表示
            await interaction.response.edit_message(
                content=f"🎒 **アイテムを支給されました！**\n\n手に入れたもの: **{item_name}**\n効果: {ITEMS[item_name]}\n\n👇 **昼の議論中、怪しいと思った人を1人選んで正体を覗き見てください！**", 
                view=MirrorUseView(game.alive_players)
            )
        else:
            await interaction.response.edit_message(
                content=f"🎒 **アイテムを支給されました！**\n\n手に入れたもの: **{item_name}**\n効果: {ITEMS[item_name]}\n\n朝の犠牲者判定や、投票フェーズで自動的に効果が発動します。大切にしまっておいてください。", 
                view=None
            )

def reset_items():
    player_items.clear()

def get_player_item(player_id):
    return player_items.get(player_id, None)

def use_player_item(player_id):
    if player_id in player_items:
        del player_items[player_id]

# 💡 main.pyでload_extensionするために必須のセットアップ関数を追加
async def setup(bot):
    pass
