import discord, random, asyncio, sys, os
from discord.ext import commands

sys.path.append(os.getcwd())

from config import game
from views import RecruitView
from actions import ActionView
import channels

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

    @commands.command()
    async def setup(self, ctx):
        game.host = ctx.author
        view = RecruitView()
        game.recruit_message = await ctx.send(embed=view.create_recruit_embed(), view=view)

    async def execute_game_start(self, channel):
        role_map = {"人狼": Werewolf, "占い師": Seer, "霊媒師": Medium, "狩人": Hunter, "怪盗": Thief, "狂人": Madman, "シリアルキラー": SerialKiller, "村人": Villager}
        deck = [role_map[n]() for n, c in game.role_settings.items() for _ in range(c)]
        
        # 役職カードが足りない場合は村人で埋める
        while len(deck) < len(game.players): 
            deck.append(Villager())
        random.shuffle(deck)
        
        # プレイヤーへの配役
        game.roles = {p: deck[i] for i, p in enumerate(game.players)}
        for p, role in game.roles.items(): 
            role.player = p
        
        # 各プレイヤーのDMへ自身の役職を通知
        for p, role in game.roles.items():
            try:
                await p.send(f"🔮 あなたの役職は 【**{role.name}**】 (陣営: {role.team}) です。")
            except:
                pass
        
        # チャンネル自動作成と権限設定
        await channels.create_game_channels(channel.guild)
        await channels.setup_wolf_permissions()
        
        game.is_playing = True
        game.alive_players = game.players.copy()
        game.thief_action_done = False
        
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
        
        # 最初の夜フェーズへ
        await self.start_night(channel)

    async def start_night(self, channel):
        game.actions = {}
        await channel.send("🌙 夜が訪れました。各役職者はBotからのDMを確認して行動を選択してください。")
        await game.log_channel.send("🌙 夜フェーズに移行しました。")
        
        # 生存している役職者へDMを送信
        for player, role in game.roles.items():
            if player not in game.alive_players: 
                continue
            label = role.get_action_label()
            if label:
                try:
                    await player.send(f"【{role.name}】の能力発動時刻です。今夜の「{label}」対象者を選んでください。", view=ActionView(player, label))
                except:
                    pass
                    
        # 設定された夜の行動時間だけ待つ
        await asyncio.sleep(game.night_time)
        await self.process_night_results(channel)

    async def process_night_results(self, channel):
        await game.log_channel.send("☀️ 朝フェーズになり、夜の行動結果を処理しています。")
        
        # 1. 怪盗の処理 (他の処理より先に処理して役職を入れ替える)
        thief_target = None
        if not game.thief_action_done:
            for actor, data in game.actions.items():
                if data['action'] == "強奪" and actor in game.alive_players:
                    target = data['target']
                    if target in game.alive_players:
                        thief_target = target
                        # 役職を入れ替える
                        actor_role = game.roles[actor]
                        target_role = game.roles[target]
                        game.roles[actor], game.roles[target] = target_role, actor_role
                        # プレイヤー参照の更新
                        game.roles[actor].player = actor
                        game.roles[target].player = target
                        try:
                            await actor.send(f"🎭 【怪盗の強奪結果】: {target.display_name} から役職を奪いました！あなたの新しい役職は 【**{target_role.name}**】 です。")
                        except:
                            pass
            game.thief_action_done = True

        # 2. 占い師の処理
        for actor, data in game.actions.items():
            if data['action'] == "占い" and actor in game.alive_players:
                target = data['target']
                # 占った時点での最新の役職(怪盗の後)をチェック
                actual_role = game.roles.get(target)
                result_team = "人狼" if (actual_role and actual_role.name == "人狼") else "人間"
                try:
                    await actor.send(f"🔮 【占い結果】: {target.display_name} を占いました。結果は 【**{result_team}**】 です。")
                except:
                    pass

        # 3. 護衛と襲撃・殺害の処理
        guarded_players = [data['target'] for actor, data in game.actions.items() if data['action'] == "護衛" and actor in game.alive_players]
        attacked_targets = []
        
        # 人狼の襲撃対象
        for actor, data in game.actions.items():
            if data['action'] == "襲撃" and actor in game.alive_players:
                if data['target'] not in attacked_targets:
                    attacked_targets.append(data['target'])
                    
        # シリアルキラーの殺害対象
        for actor, data in game.actions.items():
            if data['action'] == "殺害" and actor in game.alive_players:
                if data['target'] not in attacked_targets:
                    attacked_targets.append(data['target'])

        # 襲撃対象の中から、護衛されていないプレイヤーが犠牲者になる
        dead_list = []
        for target in attacked_targets:
            if target in guarded_players:
                await game.log_channel.send(f"🛡️ 狩人の護衛成功！ {target.display_name} への襲撃が阻止されました。")
            else:
                if target in game.alive_players:
                    dead_list.append(target)

        # 霊媒師用のログ保存（前回の処刑者がいればここで結果を溜めておくなどの拡張も可能）
        game.last_executed = None 

        # 朝の犠牲者発表
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
        else:
            msg = "昨夜は誰も犠牲になりませんでした。"
            await channel.send(f"🛡️ {msg}")
            await game.log_channel.send(f"🛡️ {msg}")

        # 毎フェーズ終了時の勝利判定チェック
        if await self.check_game_over(channel): 
            return

        # 朝の結果発表時間(演出)を待ってから議論へ
        await asyncio.sleep(game.morning_time)
        await self.start_discussion(channel)

    async def start_discussion(self, channel):
        await channel.send(f"💬 昼の議論を開始します。時間は {game.discussion_time} 秒です。生存者の皆さんは話し合ってください！")
        await game.log_channel.send("💬 昼の議論フェーズに入りました。")
        
        # 議論時間を待つ
        await asyncio.sleep(game.discussion_time)
        
        await channel.send("⏱️ 議論時間が終了しました。これより投票（処刑対象の選出）に移ります。")
        await self.start_voting(channel)

    async def start_voting(self, channel):
        await channel.send("🗳️ 生存者はメニューから本日追放するプレイヤーを1人選んで投票してください。")
        await game.log_channel.send("🗳️ 投票フェーズに入りました。")
        
        # 簡易的な投票UIをDMではなくゲームチャンネルに設置
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
                votes[target_id] = votes.get(target_id, 0) + 1
                voted_users.add(interaction.user)
                
                await interaction.response.send_message(f"【{interaction.user.display_name}】さんが投票しました。", json=None)
                
                # 全員が投票し終えたら即座に締め切る
                if len(voted_users) >= len(game.alive_players):
                    self.view.stop()

        select_menu = VoteSelect(placeholder="追放するプレイヤーを選択...", options=select_options)
        view.add_item(select_menu)
        
        vote_msg = await channel.send("👇 ここから投票してください", view=view)
        
        # 最大60秒待つ、または全員が投票完了するまで待機
        await view.wait()
        try:
            await vote_msg.edit(content="🗳️ 投票が締め切られました。", view=None)
        except:
            pass

        # 投票結果の集計
        if not votes:
            await channel.send("誰も投票しなかったため、本日の処刑は行われません。")
            await game.log_channel.send("🗳️ 投票がなかったため、処刑なし。")
        else:
            most_voted_id = max(votes, key=votes.get)
            executed_user = channel.guild.get_member(most_voted_id)
            if not executed_user:
                executed_user = await channel.guild.fetch_member(most_voted_id)

            if executed_user and executed_user in game.alive_players:
                game.alive_players.remove(executed_user)
                game.last_executed = executed_user  # 霊媒師用
                await channel.send(f"⚖️ 投票の結果、本日は 【**{executed_user.display_name}**】 が村から追放されました。")
                await game.log_channel.send(f"⚖️ 処刑: {executed_user.display_name} (投票数: {votes[most_voted_id]})")
                await channels.handle_player_death_vc(executed_user)
                
                # 霊媒師への通知処理
                for p, role in game.roles.items():
                    if p in game.alive_players and role.name == "霊媒師":
                        ex_role = game.roles.get(executed_user)
                        ex_result = "人狼" if (ex_role and ex_role.name == "人狼") else "人間"
                        try:
                            await p.send(f"👻 【霊媒結果】: 本日処刑された {executed_user.display_name} は 【**{ex_result}**】 でした。")
                        except:
                            pass

        # 処刑後の勝利判定チェック
        if await self.check_game_over(channel): 
            return

        # 次の夜フェーズへループ
        await self.start_night(channel)

    async def check_game_over(self, channel):
        victory_message = game.check_victory()
        if victory_message:
            game.is_playing = False
            
            # 全プレイヤーの本当の役職を明かすエンベデッドメッセージ
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

async def setup(bot): 
    await bot.add_cog(GameCog(bot))
