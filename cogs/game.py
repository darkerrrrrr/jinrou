# cogs/game.py
import discord
from discord.ext import commands
import asyncio
import random
from collections import Counter
from config import game
from views import RecruitView

from discord.ui import View, Select

# 各個別役職ファイルのインポート
from roles.wolf import Werewolf
from roles.serial_killer import SerialKiller
from roles.seer import Seer
from roles.medium import Medium
from roles.hunter import Hunter
from roles.thief import Thief
from roles.madman import Madman
from roles.villager import Villager

class GameCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def mute_all_alive(self, mute_status: bool, reason: str):
        """【自動ミュート制御】生存している全プレイヤーのミュート状態を切り替える"""
        for member in game.alive_players:
            if member.voice and member.voice.channel:
                try:
                    await member.edit(mute=mute_status, reason=reason)
                except discord.Forbidden:
                    print(f"⚠️ 権限不足により {member.display_name} のミュート状態を変更できませんでした。")
                except Exception as e:
                    print(f"⚠️ ミュート処理エラー ({member.display_name}): {e}")

    async def handle_death(self, member: discord.Member):
        """死亡者の処理（ニックネーム変更、霊界VCへの自動移動、霊界チャットの解放）"""
        if member in game.alive_players:
            game.alive_players.remove(member)
            
            try:
                await member.edit(nick=f"[死亡] {member.display_name}")
            except discord.Forbidden:
                pass

            if member.voice and member.voice.channel:
                guild = member.guild
                # ★【修正】名前に「霊界」という文字が含まれているVCを自動で見つける（部分一致対応）
                reikai_vc = next((vc for vc in guild.voice_channels if "霊界" in vc.name), None)
                
                if reikai_vc:
                    try:
                        await member.edit(mute=False, voice_channel=reikai_vc, reason="死亡による霊界VCへの強制移動")
                    except discord.Forbidden:
                        print(f"⚠️ 権限不足により {member.display_name} を霊界VCに移動できませんでした。")
                else:
                    await game.log_channel.send("⚠️ サーバー内に「霊界」という名前のボイスチャンネルが見つからないため、自動移動がスキップされました。")
            
            if game.dead_channel:
                await game.dead_channel.set_permissions(member, read_messages=True, send_messages=True)
                await game.dead_channel.send(f"👻 {member.mention} さんが霊界（VC·チャット）に送られました。ここからは死者同士で自由に会話·通話が可能です！")

            await game.log_channel.send(f"【死亡通知】 {member.mention} さんが死亡しました。")

    def calc_night_result(self):
        """夜のアクション結果を集計して犠牲者を割り出す"""
        killed_target = None
        protected_target = None
        sk_killed_target = None
        
        for actor, target in game.actions.items():
            role_obj = game.roles.get(actor)
            if role_obj and role_obj.name == "狩人":
                protected_target = target
                break
        for actor, target in game.actions.items():
            role_obj = game.roles.get(actor)
            if role_obj and role_obj.name == "人狼":
                if target != protected_target:
                    killed_target = target
                break
        for actor, target in game.actions.items():
            role_obj = game.roles.get(actor)
            if role_obj and role_obj.name == "シリアルキラー":
                sk_killed_target = target
                break
        
        return sk_killed_target if sk_killed_target else killed_target

    async def run_game_loop(self):
        """メイン進行ループ"""
        day_count = 0
        
        while game.is_playing:
            
            # ====================================================
            # 1. 朝·昼（議論）フェーズ
            # ====================================================
            if day_count == 0:
                await game.log_channel.send(f"🌅 【0日目：朝】が始まりました！\n配役を確認し、生存者同士で軽く顔合わせを行ってください。（時間: 30秒）\n※0日目の朝は、投票や処刑はありません。")
                await asyncio.sleep(30)
            else:
                await game.log_channel.send(f"🌅 【{day_count}日目：朝】になりました。昨晩の結果を発表します。")
                
                if day_count > 1 and game.last_executed:
                    for member in game.alive_players:
                        role_obj = game.roles.get(member)
                        if role_obj and role_obj.name == "霊媒師":
                            await role_obj.send_medium_result(game.last_executed, game.last_executed_role_name)

                killed_player = self.calc_night_result()
                if killed_player and day_count > 1:
                    await self.handle_death(killed_player)
                else:
                    await game.log_channel.send("昨晩の犠牲者はありません。")
                
                game.actions.clear()
                
                alive_names = [p.display_name for p in game.alive_players]
                await game.log_channel.send(f"現在の生存者 ({len(game.alive_players)}名): {', '.join(alive_names)}")
                
                winner = game.check_victory()
                if winner:
                    await self.mute_all_alive(mute_status=False, reason="ゲーム終了によるミュート解除")
                    await game.log_channel.send(f"🏁 ゲーム終了: {winner}\n※霊界チャットの削除、ニックネーム戻し、生存者のVC戻しは手動で行ってください。")
                    game.is_playing = False
                    break
                    
                await asyncio.sleep(game.morning_time)

                await game.log_channel.send(f"🗣️ 【{day_count}日目：議論】を開始します。（制限時間: {game.discussion_time}秒）")
                if game.discussion_time > 10:
                    await asyncio.sleep(game.discussion_time - 10)
                    await game.log_channel.send("⏱️ 議論終了 10秒前 です。")
                    await asyncio.sleep(10)
                else:
                    await asyncio.sleep(game.discussion_time)
                
                # ====================================================
                # 2. 投票·処刑フェーズ
                # ====================================================
                await game.log_channel.send(f"⚖️ 議論時間が終了しました。投票フェーズに移ります。")
                
                vote_view = View(timeout=60)
                votes_data = {} 
                voted_users = set()
                
                class DynamicVoteSelect(Select):
                    async def callback(self, interaction: discord.Interaction):
                        if interaction.user not in game.alive_players:
                            return await interaction.response.send_message("死亡しているため投票できません。", ephemeral=True)
                        if interaction.user.id in voted_users:
                            return await interaction.response.send_message("すでに投票を完了しています。", ephemeral=True)
                        
                        target_id = int(self.values[0])
                        votes_data[interaction.user.id] = target_id
                        voted_users.add(interaction.user.id)
                        
                        await interaction.response.send_message(f"投票を受け付けました。", ephemeral=True)
                        if len(voted_users) >= len(game.alive_players):
                            vote_view.stop()

                options = [discord.SelectOption(label=p.display_name, value=str(p.id)) for p in game.alive_players]
                select_item = DynamicVoteSelect(placeholder="処刑したい相手を1人選んでください...", options=options)
                vote_view.add_item(select_item)
                
                vote_banner = await game.log_channel.send(f"🗳️ 生存者は下のメニューから処刑したいプレイヤーへ投票してください。（制限時間: 60秒）", view=vote_view)
                
                await vote_view.wait()
                try: await vote_banner.delete()
                except Exception: pass
                
                if not votes_data:
                    await game.log_channel.send("⚠️ 誰も投票しなかったため、本日の処刑はスキップされます。")
                else:
                    target_counts = Counter(votes_data.values())
                    max_votes = max(target_counts.values())
                    most_voted_ids = [tid for tid, count in target_counts.items() if count == max_votes]
                    
                    final_target_id = random.choice(most_voted_ids)
                    executed_member = self.bot.get_guild(game.log_channel.guild.id).get_member(final_target_id)
                    
                    if executed_member:
                        await game.log_channel.send(f"⚖️ 集計の結果、最多得票の 【{executed_member.display_name}】 さんの処刑が決まりました。")
                        game.last_executed = executed_member
                        game.last_executed_role_name = game.roles[executed_member].name
                        await self.handle_death(executed_member)
                        
                        winner = game.check_victory()
                        if winner:
                            await self.mute_all_alive(mute_status=False, reason="ゲーム終了によるミュート解除")
                            await game.log_channel.send(f"🏁 ゲーム終了: {winner}\n※霊界チャットの削除、ニックネーム戻し、生存者のVC戻しは手動で行ってください。")
                            game.is_playing = False
                            break
                    else:
                        await game.log_channel.send("⚠️ 対象のプレイヤーが見つかりませんでした。")
                
                await game.log_channel.send("次の夜フェーズへ移行します...")

            # ====================================================
            # 3. 夜フェーズ（自動ミュート開始）
            # ====================================================
            await game.log_channel.send(f"🌙 【{day_count}日目：夜】を開始します。（行動時間: {game.night_time}秒）\n🔊 生存メンバーを全員ミュートしました。各自DMのメニューを確認して行動してください。")
            await self.mute_all_alive(mute_status=True, reason="夜フェーズ開始によるミュート")

            if day_count == 0:
                wolves = [m.display_name for m, r in game.roles.items() if r.name == "人狼"]
                madmen = [m.display_name for m, r in game.roles.items() if r.name == "狂人"]
                
                for member, role_obj in game.roles.items():
                    if role_obj.name == "人狼":
                        wolf_msg = f"🐺【人狼の仲間確認】\n今回の人狼はあなたを含めて以下のメンバーです：\n・" + "\n・".join(wolves)
                        if madmen:
                            wolf_msg += f"\n\n※今回の狂人は 【{', '.join(madmen)}】 さんです。"
                        await member.send(wolf_msg)
                        
                    elif role_obj.name == "狂人":
                        mad_msg = f"🤡【狂人のご主人様確認】\nあなたが今回味方すべき「人狼」は以下のメンバーです：\n・" + "\n・".join(wolves)
                        await member.send(mad_msg)

                # 怪盗の処理
                game.thief_action_done = False
                thief_member = None
                for m, r in game.roles.items():
                    if r.name == "怪盗":
                        thief_member = m
                        break
                
                if thief_member:
                    await game.roles[thief_member].send_thief_menu(game.players)
                    w = 0
                    while not game.thief_action_done and w < 30:
                        await asyncio.sleep(2)
                        w += 2
            
            for member in game.alive_players:
                role_obj = game.roles.get(member)
                if role_obj:
                    await role_obj.send_night_menu(game.alive_players)
            
            await asyncio.sleep(game.night_time)
            
            game.thief_action_done = True
            day_count += 1

    @commands.command()
    async def recruit(self, ctx):
        if game.is_playing:
            return await ctx.send("エラー: すでにゲームが進行中です。")
        game.players = []
        game.roles.clear()
        game.log_channel = ctx.channel
        await ctx.send("🐺 人狼ゲームの参加者を募集します。ボタンを押して参加してください。", view=RecruitView())

    @commands.command()
    async def start_game(self, ctx):
        if len(game.players) < 3:
            return await ctx.send("エラー: 3人以上集まらないと開始できません。")
            
        role_pool_classes = []
        role_mapping = {
            "人狼": Werewolf, "シリアルキラー": SerialKiller, "占い師": Seer, 
            "霊媒師": Medium, "狩人": Hunter, "怪盗": Thief, "狂人": Madman, "村人": Villager
        }
        
        for role_name, count in game.role_settings.items():
            for _ in range(count):
                role_pool_classes.append(role_mapping[role_name])
                
        if len(game.players) != len(role_pool_classes):
            return await ctx.send(
                f"❌ エラー: 参加人数({len(game.players)}人) と 設定役職総数({len(role_pool_classes)}枚) が一致していません！"
            )

        game.is_playing = True
        game.alive_players = game.players.copy()
        random.shuffle(role_pool_classes)
        
        for member, role_cls in zip(game.players, role_pool_classes):
            role_instance = role_cls(member)
            game.roles[member] = role_instance
            await member.send(f"ゲームが開始されました。あなたの役職は【 {role_instance.name} 】です。")

        guild = ctx.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        game.dead_channel = await guild.create_text_channel(name="👻人狼・霊界チャット", overwrites=overwrites, category=ctx.channel.category)

        active_roles_text = ", ".join([f"{k}×{v}" for k, v in game.role_settings.items() if v > 0])
        await ctx.send(
            f"🎲 ゲームを開始しました！\n"
            f"📋 配役構成: {active_roles_text}\n"
            f"まずは【0日目：朝】の顔合わせからスタートします！"
        )
        
        self.bot.loop.create_task(self.run_game_loop())

async def setup(bot):
    await bot.add_cog(GameCog(bot))