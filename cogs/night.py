import discord, asyncio, random
from config import get_game, RoleName
from actions import ActionView
import channels
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cogs.game import GameCog

# アイテムシステム関連
from cogs.item import reset_items, ItemDrawView, get_player_item, use_player_item

async def start_night(self: 'GameCog', channel: discord.TextChannel) -> None:
    """
    夜フェーズを開始する
    
    Args:
        channel: メインチャンネル
    """
    game = get_game(channel.guild.id)
    game.actions = {}
    game.night_skip_event.clear()
    
    # 死亡したプレイヤーのアイテムを削除
    alive_ids = {p.id for p in game.alive_players}
    game.player_items = {uid: item for uid, item in game.player_items.items() if uid in alive_ids}
    
    await channels.mute_all_alive_players(channel.guild, mute_status=True)
    
    game.event_log.append(f"═══ {game.day_count}日目：夜 ═══")
    target_channel = game.progress_channel or channel # ここで定義

    # 説明文を削除し、タイトルのみでテンポを上げる
    night_embed = discord.Embed(title=f"🌙 第{game.day_count}夜：行動フェーズ", description="各役職者はDMで行動を選択してください。\n村人は明日の身支度（アイテム支給）を行ってください。", color=discord.Color.dark_blue())
    await target_channel.send(embed=night_embed)
    if game.log_channel:
        await game.log_channel.send("🌙 夜フェーズを開始しました。")
    await game.save_state(channel.guild)
    
    for player, role in game.roles.items():
        if player not in game.alive_players: 
            continue
            
        # 霊媒師への自動通知（前日に処刑された人がいる場合）
        if role.name == RoleName.MEDIUM:
            if game.last_executed:
                actual_role = game.roles.get(game.last_executed)
                result_team = "人狼" if (actual_role and actual_role.name == RoleName.WOLF) else "人間"
                try:
                    m_msg = await player.send(f"👻 【霊媒結果】: 昨日追放された {game.last_executed.display_name} は 【**{result_team}**】 でした。")
                    game.add_dm_message(player.id, m_msg.id)
                except: pass
            else:
                try:
                    await player.send("👻 【霊媒結果】: 昨日追放された人はいませんでした。")
                except: pass
        
        label = role.get_action_label()
        if label:
            try:
                view = ActionView(player, label, timeout=game.night_time)
                msg = await player.send(f"【{role.name}】の能力発動時刻です。今夜の「{label}」対象者を選んでください。", view=view)
                game.add_dm_message(player.id, msg.id)
                view.message = msg # タイムアウト時にメッセージを編集できるように保持
            except Exception as e:
                print(f"⚠️ {player.display_name} ({role.name}) への能力通知DM失敗: {e}")
                if game.log_channel:
                    await game.log_channel.send(f"⚠️ {player.mention} ({role.name}) へのDM送信に失敗しました。")
                # DM失敗時は「行動なし」として登録し、進行を妨げないようにする
                game.actions[player] = {"action": "skipped", "target": None}
                game.check_night_actions_complete()
        elif role.name == RoleName.VILLAGER:
            # 普通の村人のみにアイテム支給ガチャボタンを送信
            try:
                i_msg = await player.send("🎒 **【夜間の身支度】** 明日の過酷な議論に備え、手荷物を確認しましょう。下のボタンからアイテムを1つ獲得できます。", view=ItemDrawView(timeout=game.night_time))
                game.add_dm_message(player.id, i_msg.id)
            except Exception as e:
                print(f"⚠️ {player.display_name} へのアイテムガチャDM失敗: {e}")
                if game.log_channel:
                    await game.log_channel.send(f"⚠️ {player.mention} へのアイテムガチャDMに失敗しました。")
                # DM失敗時はダミーアイテムを登録して進行を妨げないようにする
                game.player_items[player.id] = "❌ 準備失敗"
                game.check_night_actions_complete()
                
    # 固定時間の待機ではなく、全員完了またはタイムアウトまで待機
    try:
        await asyncio.wait_for(game.night_skip_event.wait(), timeout=game.night_time)
    except asyncio.TimeoutError:
        pass

    await self.process_night_results(channel)


async def process_night_results(self: 'GameCog', channel: discord.TextChannel) -> None:
    """
    夜の行動結果を処理する
    
    Args:
        channel: メインチャンネル
    """
    game = get_game(channel.guild.id)
    if game.log_channel:
        await game.log_channel.send("☀️ 朝フェーズになり、夜の行動結果を処理しています。")
    
    # 【怪盗の強奪処理】
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
                    
                    # 【拡張】アイテムも完全に入れ替える
                    actor_item = game.player_items.pop(actor.id, None)
                    target_item = game.player_items.pop(target.id, None)
                    if target_item: game.player_items[actor.id] = target_item
                    if actor_item: game.player_items[target.id] = actor_item

                    # もし人狼を奪った場合、人狼チャットを見れるように権限を更新
                    if target_role.name == RoleName.WOLF:
                        await channels.setup_wolf_permissions(channel.guild)

                    try:
                        t_msg = await actor.send(f"🎭 【怪盗の強奪結果】: {target.display_name} から役職を奪いました！あなたの新しい役職は 【**{target_role.name}**】 です。")
                        game.add_dm_message(actor.id, t_msg.id)
                    except Exception as e:
                        print(f"⚠️ {actor.display_name} (怪盗) への結果通知DM失敗: {e}")
        game.thief_action_done = True

    # 【役職ごとのアクション結果通知と集計】
    attacked_targets = set()
    guarded_targets = set()
    current_protected = {} # 今回の護衛記録
    wolf_attack_candidates = []

    for actor, data in game.actions.items():
        if actor not in game.alive_players: continue
            
        action = data.get('action')
        target = data.get('target')
        if not target: continue

        # 生存確認
        if target not in game.alive_players and action != "強奪": continue # 死亡者へのアクションは基本無効

        if action == "占い":
            actual_role = game.roles.get(target)
            result_team = "人狼" if (actual_role and actual_role.name == RoleName.WOLF) else "人間"
            game.event_log.append(f"🔮 占い師 {actor.display_name} → {target.display_name}：{result_team}")
            try:
                s_msg = await actor.send(f"🔮 【占い結果】: {target.display_name} を占いました。結果は 【**{result_team}**】 です。")
                game.add_dm_message(actor.id, s_msg.id)
            except Exception as e:
                print(f"⚠️ {actor.display_name} (占い師) への占い結果通知DM失敗: {e}")
        elif action == "混乱":
            game.confused_players.add(target.id)
            if game.log_channel:
                await game.log_channel.send(f"🌀 {actor.display_name} が {target.display_name} を混乱させました。")
            game.event_log.append(f"🌀 狂人 {actor.display_name} → {target.display_name} を混乱させた")
            try:
                c_msg = await actor.send(f"🌀 【混乱成功】: {target.display_name} を混乱させました。")
                game.add_dm_message(actor.id, c_msg.id)
            except: pass
        elif action == "護衛":
                guarded_targets.add(target)
                current_protected[actor.id] = target.id # 護衛対象を記録
                game.event_log.append(f"🛡️ 狩人 {actor.display_name} → {target.display_name} を護衛")
        elif action == "襲撃":
                wolf_attack_candidates.append(target)
        elif action == "殺害":
                game.event_log.append(f"🔪 シリアルキラー {actor.display_name} → {target.display_name} を殺害")
                attacked_targets.add(target)

    # 今回の護衛記録を保存（次夜の制限に使用）
    game.last_protected = current_protected

    # 人狼の襲撃先を1つに決定
    if wolf_attack_candidates:
        chosen_target = random.choice(wolf_attack_candidates)
        attacked_targets.add(chosen_target)
        game.event_log.append(f"🐺 人狼の襲撃 → {chosen_target.display_name}")

    # 【死亡判定】
    dead_list = []
    for target in attacked_targets:
        if target in guarded_targets:
            if game.log_channel:
                await game.log_channel.send(f"🛡️ 護衛成功！ {target.display_name} への襲撃が阻止されました。")
        else:
            if target in game.alive_players:
                # 【アイテム効果】お守りを持っていれば、身代わりにして襲撃を耐える
                if get_player_item(channel.guild.id, target.id) == "🛡️ お守り":
                    if game.log_channel:
                        await game.log_channel.send(f"✨ {target.display_name} は懐の「お守り」が身代わりとなり、人狼の襲撃を耐え抜いた！")
                    use_player_item(channel.guild.id, target.id) 
                    continue
                
                dead_list.append(target)

    game.last_executed = None 


    # 【死亡者発表】
    if dead_list:
        await asyncio.sleep(2) # 犠牲者がいる場合のみタメを作る
        embed = discord.Embed(title="☀️ 朝の結果発表", color=discord.Color.red())
        names = []
        for p in dead_list:
            if p in game.alive_players: 
                game.alive_players.remove(p)
            names.append(p.display_name)
            await channels.handle_player_death_vc(p, channel.guild)
        
        embed.description = f"❌ 昨夜の犠牲者: **{', '.join(names)}**"
        await target_channel.send(embed=embed)
        if game.log_channel:
            await game.log_channel.send(f"❌ 犠牲者: {', '.join(names)}")
        
        # 【アイテム効果】死んだ人が「遺言ノート」を持っていたら自動発動
        for p in dead_list:
            player_id = p.id
            if get_player_item(channel.guild.id, player_id) == "📝 遺言ノート":
                will_content = game.will_notes.get(player_id, "（何も書かれていなかった...）")
                will_embed = discord.Embed(
                    title=f"📖 {p.display_name}の遺言",
                    description=f"*{will_content}*",
                    color=discord.Color.light_grey()
                )
                await target_channel.send(embed=will_embed)
                use_player_item(channel.guild.id, player_id)
    else:
        embed = discord.Embed(title="☀️ 朝の結果発表", color=discord.Color.green())
        embed.description = "🛡️ 昨夜は誰も犠牲になりませんでした。"
        await target_channel.send(embed=embed)
        if game.log_channel:
            await game.log_channel.send("🛡️ 犠牲者なし")

    if await self.check_game_over(channel): 
        return

    game.day_count += 1
    await game.save_state(channel.guild) # 死亡処理と日付更新を保存
    await asyncio.sleep(game.morning_time)
    await self.start_discussion(channel)

# Discord.py の拡張ロードシステム用関数
async def setup(bot):
    pass
