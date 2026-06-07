import discord, random, asyncio, sys, os
from discord.ext import commands

sys.path.append(os.getcwd())

from config import game
from views import RecruitView
from actions import ActionView
import channels

# アイテムシステム関連の関数・データをインポート
from cogs.item import reset_items, ItemDrawView, get_player_item, use_player_item, silenced_players

from roles.werewolf import Werewolf
from roles.seer import Seer
from roles.medium import Medium
from roles.hunter import Hunter
from roles.thief import Thief
from roles.madman import Madman
from roles.serial_killer import SerialKiller
from roles.villager import Villager

class GameCog(commands.Cog):
    def __init__(self, bot): 
        self.bot = bot

    # 💡 コマンド名を「game_setup」に変更し、Discord.pyのシステム用setup関数との衝突を防止
    # サーバー上での入力は「!game_setup」になります
    @commands.command(name="game_setup")
    async def game_setup(self, ctx):
        game.is_playing = False
        game.players = []            
        game.roles = {}              
        game.alive_players = []      
        game.actions = {}
        game.last_executed = None
        game.last_executed_role_name = None
        game.thief_action_done = False
        game.recruit_message = None

        game.host = ctx.author
        view = RecruitView()
        game.recruit_message = await ctx.send(embed=view.create_recruit_embed(), view=view)

    async def execute_game_start(self, channel):
        role_map = {"人狼": Werewolf, "占い師": Seer, "霊媒師": Medium, "狩人": Hunter, "怪盗": Thief, "狂人": Madman, "シリアルキラー": SerialKiller, "村人": Villager}
        deck = [role_map[n]() for n, c in game.role_settings.items() for _ in range(c)]
        
        while len(deck) < len(game.players): 
            deck.append(Villager())
        random.shuffle(deck)
        
        game.roles = {p: deck[i] for i, p in enumerate(game.players)}
        for p, role in game.roles.items(): 
            role.player = p
        
        for p, role in game.roles.items():
            try:
                await p.send(f"🔮 あなたの役職は 【**{role.name}**】 (陣営: {role.team}) です。")
            except:
                pass
        
        await channels.create_game_channels(channel.guild)
        await channels.setup_wolf_permissions()
        
        game.is_playing = True
        game.alive_players = game.players.copy()
        game.thief_action_done = False
        
        # アイテム(拡声器など)が発動したときに全体通知を送るチャンネルを記憶
        game.text_channel = channel 
        silenced_players.clear() # ミュートプレイヤーリストの初期化
        
        start_message = (
            f"ゲームを開始しました。\n"
            f"【テキスト】\n"
            f"・人狼用: {game.wolf_channel.mention}\n"
            f"・ログ用: {game.log_channel.mention}\n\n"
            f"【ボイス】\n"
            f"・生存者用: {game.alive_vc.mention}\n"
            f"・墓場用: {game.dead_vc.mention}\n"
            f"※プレイヤーは生存者ボイスチャンネルに移動してください。"
        )
        await channel.send(start_message)
        await game.log_channel.send("─── ゲームログの記録を開始しました ───")
        
        await self.start_night(channel)

    async def start_night(self, channel):
        game.actions = {}
        
        # 毎晩の最初に、前夜に引いたアイテムデータをリセット
        reset_items()
        
        await channels.mute_all_alive_players(mute_status=True)
        
        await channel.send("🌙 夜が訪れました。各役職者は行動を、村人は明日の身支度（アイテム支給）を行ってください。")
        await game.log_channel.send("🌙 夜フェーズに移行しました。")
        
        for player, role in game.roles.items():
            if player not in game.alive_players: 
                continue
            
            label = role.get_action_label()
            if label:
                try:
                    await player.send(f"【{role.name}】の能力発動時刻です。今夜の「{label}」対象者を選んでください。", view=ActionView(player, label))
                except:
                    pass
            elif role.name == "村人":
                # 普通の村人のみにアイテム支給ガチャボタンを送信
                try:
                    await player.send("🎒 **【夜間の身支度】** 明日の過酷な議論に備え、手荷物を確認しましょう。下のボタンからアイテムを1つ獲得できます。", view=ItemDrawView())
                except:
                    pass
                    
        await asyncio.sleep(game.night_time)
        await self.process_night_results(channel)

    async def process_night_results(self, channel):
        await game.log_channel.send("☀️ 朝フェーズになり、夜の行動結果を処理しています。")
        
        thief_target = None
        if not game.thief_action_done:
            for actor, data in game.actions.items():
                if data['action'] == "強奪" and actor in game.alive_players:
                    target = data['target']
                    if target in game.alive_players:
                        thief_target = target
                        actor_role = game.roles[actor]
                        target_role = game.roles[target]
                        game.roles[actor], game.roles[target] = target_role, actor_role
                        game.roles[actor].player = actor
                        game.roles[target].player = target
                        try:
                            await actor.send(f"🎭 【怪盗の強奪結果】: {target.display_name} から役職を奪いました！あなたの新しい役職は 【**{target_role.name}**】 です。")
                        except:
                            pass
            game.thief_action_done = True

        for actor, data in game.actions.items():
            if data['action'] == "占い" and actor in game.alive_players:
                target = data['target']
                actual_role = game.roles.get(target)
                result_team = "人狼" if (actual_role and actual_role.name == "人狼") else "人間"
                try:
                    await actor.send(f"🔮 【占い結果】: {target.display_name} を占いました。結果は 【**{result_team}**】 です。")
                except:
                    pass

        guarded_players = [data['target'] for actor, data in game.actions.items() if data['action'] == "護衛" and actor in game.alive_players]
        attacked_targets = []
        
        for actor, data in game.actions.items():
            if data['action'] == "襲撃" and actor in game.alive_players:
                if data['target'] not in attacked_targets:
                    attacked_targets.append(data['target'])
                    
        for actor, data in game.actions.items():
            if data['action'] == "殺害" and actor in game.alive_players:
                if data['target'] not in attacked_targets:
                    attacked_targets.append(data['target'])

        dead_list = []
        for target in attacked_targets:
            if target in guarded_players:
                await game.log_channel.send(f"🛡️ 狩人の護衛成功！ {target.display_name} への襲撃が阻止されました。")
            else:
                if target in game.alive_players:
                    # 【アイテム効果】お守りを持っていれば、身代わりにして襲撃を耐える
                    if get_player_item(target.id) == "🛡️ お守り":
                        await game.log_channel.send(f"✨ {target.display_name} は懐の「お守り」が身代わりとなり、人狼の襲撃を耐え抜いた！")
                        use_player_item(target.id) 
                        continue
                    
                    dead_list.append(target)

        game.last_executed = None 

        await channel.send("☀️ 朝になりました。昨夜の行動結果を発表します。")
        await asyncio.sleep(2)

        if dead_list:
            for p in dead_list:
                if p in game.alive_players: 
                    game.alive_players.remove(p)
                await channels.handle_player_death_vc(p)
            
            result_str = "昨夜の犠牲者: " + ", ".join([p.display_name for p in dead_list])
            await channel.send(f"❌ {result_str}")
            await game.log_channel.send(f"❌ 犠牲者: {result_str}")
            
            # 【アイテム効果】死んだ人が「遺言ノート」を持っていたら自動発動
            for p in dead_list:
                if get_player_item(p.id) == "📝 遺言ノート":
                    await channel.send(f"📖 **{p.display_name}の遺言ノートが見つかりました：**\n*「私が死んだということは、人狼はあいつか……？ 村の皆、仇を取ってくれ……！」*")
                    use_player_item(p.id)
        else:
            msg = "昨夜は誰も犠牲になりませんでした。"
            await channel.send(f"🛡️ {msg}")
            await game.log_channel.send(f"🛡️ {msg}")

        if await self.check_game_over(channel): 
            return

        await asyncio.sleep(game.morning_time)
        await self.start_discussion(channel)

    async def start_discussion(self, channel):
        # 【アイテム効果】「沈黙の御札」を貼られている人はミュートを解除しない
        alive_listeners = []
        for p in game.alive_players:
            if p.id in silenced_players:
                try:
                    await p.edit(mute=True) # VCミュート維持
                except: pass
                await channel.send(f"🤐 **{p.display_name} さんは「沈黙の御札」の呪いにより、今日の議論での発言・チャットが禁止されています！**")
            else:
                alive_listeners.append(p)
                
        # 呪いにかかっていない生存者のミュートを解除
        for p in alive_listeners:
            try:
                await p.edit(mute=False)
            except: pass

        await channel.send(f"💬 昼の議論を開始します。時間は {game.discussion_time} 秒です。生存者の皆さんは話し合ってください！")
        await game.log_channel.send("💬 昼の議論フェーズに入りました。")
        
        await asyncio.sleep(game.discussion_time)
        
        await channels.mute_all_alive_players(mute_status=True)
        silenced_players.clear() 

        await channel.send("⏱️ 議論時間が終了しました。これより投票（処刑対象の選出）に移ります。")
        await self.start_voting(channel)

    async def start_voting(self, channel):
        await channel.send("🗳️ 生存者はメニューから本日追放するプレイヤーを1人選んで投票してください。")
        await game.log_channel.send("🗳️ 投票フェーズに入りました。")
        
        view = discord.ui.View(timeout=60)
        select_options = [discord.SelectOption(label=p.display_name, value=str(p.id)) for p in game.alive_players]
        
        votes = {}
        voted_users = set()

        class VoteSelect(discord.ui.Select):
            async def callback(self, interaction: discord.Interaction):
                if interaction.user not in game.alive_players:
                    return await interaction.response.send_message("生存者のみ投票可能です。", ephemeral=True)
                if interaction.user in voted_users:
                    return await interaction.response.send_message("既に投票済みです。", ephemeral=True)
                
                target_id = int(self.values[0])
                target_member = interaction.guild.get_member(target_id)
                voted_users.add(interaction.user)
                
                # 【アイテム効果】「泥団子」を持っていた場合、相手の投票権を奪う
                if get_player_item(interaction.user.id) == "🍯 泥団子":
                    use_player_item(interaction.user.id)
                    voted_users.add(target_member) 
                    await interaction.response.send_message(f"🍯 **【泥団子発動】** {interaction.user.display_name} さんが {target_member.display_name} さんに泥団子を投げつけ、今日の投票権を奪いました！")
                    await game.log_channel.send(f"🍯 {interaction.user.display_name} が {target_member.display_name} の投票権を剥奪しました。")
                    
                    if len(voted_users) >= len(game.alive_players):
                        self.view.stop()
                    return

                # 【アイテム効果】「沈黙の御札」を持っていた場合、相手に翌日の沈黙の呪いをかける
                if get_player_item(interaction.user.id) == "🤐 沈黙の御札":
                    use_player_item(interaction.user.id)
                    silenced_players.add(target_id)
                    await interaction.response.send_message(f"🤐 **【沈黙の御札発動】** {interaction.user.display_name} さんが {target_member.display_name} さんに呪いの札を貼りました！明日彼は喋れません。")
                    await game.log_channel.send(f"🤐 {interaction.user.display_name} が {target_member.display_name} に翌日の沈黙呪いを付与しました。")

                # 【アイテム効果】「疑惑の劇薬」を持っていた場合、投票ポイントを「2票分」にする
                vote_power = 1
                if get_player_item(interaction.user.id) == "🧪 疑惑の劇薬":
                    vote_power = 2
                    use_player_item(interaction.user.id)
                    await game.log_channel.send(f"🧪 {interaction.user.display_name} は「疑惑の劇薬」により2票分を投票しました。")
                
                votes[target_id] = votes.get(target_id, 0) + vote_power
                await interaction.response.send_message(f"【{interaction.user.display_name}】さんが投票しました。")
                
                if len(voted_users) >= len(game.alive_players):
                    self.view.stop()

        select_menu = VoteSelect(placeholder="追放するプレイヤーを選択...", options=select_options)
        view.add_item(select_menu)
        
        vote_msg = await channel.send("👇 ここから投票してください", view=view)
        
        await view.wait()
        try:
            await vote_msg.edit(content="🗳️ 投票が締め切られました。", view=None)
        except:
            pass

        if not votes:
            await channel.send("誰も投票しなかったため、本日の処刑は行われません。")
            await game.log_channel.send("🗳️ 投票がなかったため、処刑なし。")
        else:
            max_votes_count = max(votes.values())
            most_voted_ids = [pid for pid, v in votes.items() if v == max_votes_count]
            
            # 🛠️ 同票ランダム処刑（運命のダイス）の処理
            if len(most_voted_ids) > 1:
                await channel.send("⚖️ 投票の結果、最多得票者が同数で並びました……！\n村の意見が割れたため、**運命のダイス（ランダム）**によって追放者が決定されます。")
                most_voted_id = random.choice(most_voted_ids) 
                await game.log_channel.send(f"🎲 同票（得票数: {max_votes_count}）のため、ランダム抽選を行いました。")
            else:
                most_voted_id = most_voted_ids[0]

            executed_user = channel.guild.get_member(most_voted_id)
            if not executed_user:
                executed_user = await channel.guild.fetch_member(most_voted_id)

            if executed_user and executed_user in game.alive_players:
                game.alive_players.remove(executed_user)
                game.last_executed = executed_user  
                await channel.send(f"⚖️ 運命の審判により、本日は 【**{executed_user.display_name}**】 が村から追放されました。")
                await game.log_channel.send(f"⚖️ 処刑: {executed_user.display_name} (総投票ポイント: {max_votes_count})")
                await channels.handle_player_death_vc(executed_user)
                
                for p, role in game.roles.items():
                    if p in game.alive_players and role.name == "霊媒師":
                        ex_role = game.roles.get(executed_user)
                        ex_result = "人狼" if (ex_role and ex_role.name == "人狼") else "人間"
                        try:
                            await p.send(f"👻 【霊媒結果】: 本日処刑された {executed_user.display_name} は 【**{ex_result}**】 でした。")
                        except:
                            pass

        if await self.check_game_over(channel): 
            return

        await self.start_night(channel)

    async def check_game_over(self, channel):
        victory_message = game.check_victory()
        if victory_message:
            game.is_playing = False
            await channels.mute_all_alive_players(mute_status=False)
            
            embed = discord.Embed(title="🏁 ゲーム終了！ 最終結果", color=discord.Color.gold(), description=f"🏆 **{victory_message}**")
            roles_reveal = ""
            for p, role in game.roles.items():
                status = "🟢 生存" if p in game.alive_players else "💀 死亡"
                roles_reveal += f"・{p.mention} : **{role.name}** ({status})\n"
            embed.add_field(name="👥 全員の配役", value=roles_reveal)
            
            await channel.send(embed=embed)
            await game.log_channel.send(f"🏁 ゲームが終了しました。結果: {victory_message}")
            await game.log_channel.send("─── ゲームログの記録を終了しました ───")
            return True
        return False

# 💡 Discord.pyの拡張ロードシステム用関数（これで競合しません）
async def setup(bot): 
    await bot.add_cog(GameCog(bot))
