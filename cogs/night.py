import discord, asyncio, random
from config import get_game, RoleName
from actions import ActionView
import channels
from typing import TYPE_CHECKING, cast
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
    
    # 🌙 夜は全員「喋れない」状態に強制設定（マイクミュートのみ）
    await channels.mute_all_alive_players(channel.guild, mute_status=True)
    game.vc_locked = True
    
    game.event_log.append(f"═══ {game.day_count}日目：夜 ═══")
    target_channel = game.progress_channel or channel # ここで定義

    # 説明文を削除し、タイトルのみでテンポを上げる
    night_embed = discord.Embed(title=f"🌙 第{game.day_count}夜：行動フェーズ", description="各役職者はDMで行動を選択してください。\n村人は明日の身支度（アイテム支給）を行ってください。", color=discord.Color.dark_blue())
    await target_channel.send(embed=night_embed, silent=True)

    # 人狼と霊界のスレッドに通知ありでメッセージを送る
    if game.wolf_thread:
        embed = discord.Embed(title=f"🌙 第{game.day_count}夜：作戦会議", description="襲撃先を相談してください。", color=discord.Color.dark_magenta())
        await game.wolf_thread.send(embed=embed, silent=True)
    if game.dead_thread:
        embed = discord.Embed(title=f"🌙 第{game.day_count}夜：観戦", description="生存者たちの行動を見守りましょう。", color=discord.Color.dark_blue())
        await game.dead_thread.send(embed=embed, silent=True)

    if game.log_channel:
        await game.log_channel.send(embed=discord.Embed(description="🌙 夜フェーズを開始しました。", color=discord.Color.blue()))
    await game.save_state(channel.guild)
    
    for player, role in game.roles.items():
        if player not in game.alive_players: 
            continue
            
        # 霊媒師への自動通知（前日に処刑された人がいる場合）
        if role.name == RoleName.MEDIUM:
            if game.last_executed:
                actual_role = game.roles.get(game.last_executed)
                result_team = "人狼" if (actual_role and actual_role.name == RoleName.WOLF) else "人間"
                m_embed = discord.Embed(title="👻 霊媒結果", description=f"昨日追放された {game.last_executed.display_name} は 【**{result_team}**】 でした。", color=discord.Color.purple())
                try:
                    m_msg = await player.send(embed=m_embed, silent=True)
                    game.add_dm_message(player.id, m_msg.id)
                except: pass
            else:
                try:
                    await player.send(embed=discord.Embed(title="👻 霊媒結果", description="昨日追放された人はいませんでした。", color=discord.Color.light_grey()), silent=True)
                except: pass
        
        label = role.get_action_label()
        if label:
            # 初夜（第0夜）は襲撃・殺害を制限する
            if game.day_count == 0 and label in ["襲撃", "殺害"]:
                # 行動を「スキップ」として登録し、全員完了判定を回す
                game.actions[player] = {"action": "skipped", "target": None, "is_critical": False}
                game.check_night_actions_complete()
                try:
                    msg_text = "初日の夜（第0夜）は襲撃を行えません。仲間との相談に集中しましょう。" if label == "襲撃" else "初日の夜（第0夜）は殺害を行えません。明日以降に備えましょう。"
                    info_embed = discord.Embed(title=f"🌙 第0夜：{role.name}", description=msg_text, color=discord.Color.blue())
                    dm_msg = await player.send(embed=info_embed, silent=True)
                    game.add_dm_message(player.id, dm_msg.id)
                except: pass
                continue

            is_wolf = (role.name == RoleName.WOLF)
            try:
                view = ActionView(player, label, channel.guild.id, timeout=game.night_time)
                action_embed = discord.Embed(title=f"🌙 夜のアクション：{role.name}", description=f"今夜の「**{label}**」対象者を選んでください。", color=discord.Color.dark_purple())
                msg = await player.send(embed=action_embed, view=view, silent=not is_wolf)
                game.add_dm_message(player.id, msg.id)
                view.message = msg # タイムアウト時にメッセージを編集できるように保持
            except Exception as e:
                print(f"⚠️ {player.display_name} ({role.name}) への能力通知DM失敗: {e}")
                if game.log_channel:
                    await game.log_channel.send(f"⚠️ {player.mention} ({role.name}) へのDM送信に失敗しました。")
                # DM失敗時は「行動なし」として登録し、進行を妨げないようにする
                game.actions[player] = {"action": "skipped", "target": None, "is_critical": False}
                game.check_night_actions_complete()
        elif role.name == RoleName.VILLAGER:
            # 普通の村人のみにアイテム支給ガチャボタンを送信
            try:
                draw_embed = discord.Embed(title="🎒 夜間の身支度", description="明日の過酷な議論に備え、手荷物を確認しましょう。\n下のボタンからアイテムを1つ獲得できます。", color=discord.Color.blue())
                i_msg = await player.send(embed=draw_embed, view=ItemDrawView(channel.guild.id, timeout=game.night_time), silent=True)
                game.add_dm_message(player.id, i_msg.id)
            except Exception as e:
                print(f"⚠️ {player.display_name} へのアイテムガチャDM失敗: {e}")
                if game.log_channel:
                    await game.log_channel.send(f"⚠️ {player.mention} へのアイテムガチャDMに失敗しました。")
                # DM失敗時は Literal 定義に含まれる「なし」を代入して型安全を確保
                game.player_items[player.id] = "なし"
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
    target_channel = game.progress_channel or channel

    # ☀️ 朝になったタイミングで日数を進める
    game.day_count += 1

    if game.log_channel:
        await game.log_channel.send(embed=discord.Embed(description="☀️ 朝フェーズの処理を開始しました。", color=discord.Color.orange()))
    
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

                    game.event_log.append(f"🎭 怪盗 {actor.display_name} が {target.display_name} の役職({target_role.name})を奪いました")
                    try:
                        thief_embed = discord.Embed(title="🎭 強奪成功", description=f"{target.display_name} から役職を奪いました！\nあなたの新しい役職は 【**{target_role.name}**】 です。", color=discord.Color.gold())
                        t_msg = await actor.send(embed=thief_embed, silent=True)
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
            # data.get は Any を返すため、bool() でラップして型を確定させる
            is_crit = bool(data.get('is_critical', False)) 
            if is_crit:
                # クリティカル：具体的な役職がわかる
                result_str = f"【**{actual_role.name}**】"
                game.event_log.append(f"🔮 占い師 {actor.display_name} → {target.display_name}：クリティカル！({actual_role.name})")
            else:
                result_team = "人狼" if (actual_role and actual_role.name == RoleName.WOLF) else "人間"
                result_str = f"【**{result_team}**】"
                game.event_log.append(f"🔮 占い師 {actor.display_name} → {target.display_name}：{result_team}")
            
            try:
                seer_embed = discord.Embed(title="🔮 占い結果", description=f"{target.display_name} を占った結果、 {result_str} でした。" + (" (⚡クリティカル！)" if is_crit else ""), color=discord.Color.blue())
                s_msg = await actor.send(embed=seer_embed, silent=True)
                game.add_dm_message(actor.id, s_msg.id)
            except Exception as e:
                print(f"⚠️ {actor.display_name} (占い師) への占い結果通知DM失敗: {e}")
        elif action == "混乱":
            game.confused_players.add(target.id)
            if game.log_channel:
                await game.log_channel.send(embed=discord.Embed(description=f"🌀 {actor.display_name} が {target.display_name} を混乱させました。", color=discord.Color.purple()))
            game.event_log.append(f"🌀 狂人 {actor.display_name} → {target.display_name} 混乱")
            try:
                mad_embed = discord.Embed(title="🌀 混乱成功", description=f"{target.display_name} を混乱させ、投票先を狂わせました。", color=discord.Color.purple())
                c_msg = await actor.send(embed=mad_embed, silent=True)
                game.add_dm_message(actor.id, c_msg.id)
            except: pass
        elif action == "護衛":
                guarded_targets.add(target)
                if bool(data.get('is_critical', False)): # 真偽値を確実に判定
                    guarded_targets.add(actor) # クリティカル：自分も守る
                    game.event_log.append(f"🛡️ 狩人 {actor.display_name} → {target.display_name} 完璧な護衛！(自分も保護)")
                else:
                    game.event_log.append(f"🛡️ 狩人 {actor.display_name} → {target.display_name} を護衛")
                current_protected[actor.id] = target.id # 護衛対象を記録
        elif action == "襲撃":
                wolf_attack_candidates.append((target, bool(data.get('is_critical', False)))) # tuple の2番目を bool 固定
        elif action == "殺害":
                game.event_log.append(f"🔪 シリアルキラー {actor.display_name} → {target.display_name} を殺害")
                attacked_targets.add(target)

    # 今回の護衛記録を保存（次夜の制限に使用）
    game.last_protected = current_protected

    # 人狼の襲撃先を1つに決定
    if wolf_attack_candidates:
        chosen_target, is_wolf_crit = cast(tuple[discord.Member, bool], random.choice(wolf_attack_candidates))
        attacked_targets.add(chosen_target)
        if is_wolf_crit: game.event_log.append(f"🐺 人狼の強襲(貫通) → {chosen_target.display_name}")
        else: game.event_log.append(f"🐺 人狼の襲撃 → {chosen_target.display_name}")

    # 【死亡判定】
    dead_list = []
    for target in attacked_targets:
        # クリティカル襲撃かどうかを確認（人狼の襲撃候補から判定を引き継ぐ必要があるため、簡易的に全襲撃に対してチェック）
        is_pierce = any(data[1] for data in wolf_attack_candidates if data[0] == target)

        if target in guarded_targets:
            if game.log_channel:
                await game.log_channel.send(embed=discord.Embed(description=f"🛡️ 護衛成功！ {target.display_name} への襲撃が阻止されました。", color=discord.Color.green()))
        else:
            if target in game.alive_players:
                # クリティカルでない襲撃の場合のみ、お守りが有効
                if get_player_item(channel.guild.id, target.id) == "🛡️ お守り" and not is_pierce:
                    if game.log_channel:
                        await game.log_channel.send(embed=discord.Embed(description=f"✨ {target.display_name} は「お守り」により襲撃を耐え抜きました。", color=discord.Color.green()))
                    use_player_item(channel.guild.id, target.id) 
                    continue
                
                dead_list.append(target)

    game.last_executed = None 


    # 【死亡者発表】
    if dead_list:
        await asyncio.sleep(2) # 犠牲者がいる場合のみタメを作る
        embed = discord.Embed(title=f"☀️ {game.day_count}日目：朝の結果発表", color=discord.Color.red())
        # 霊界のスレッドには先に通知を送って準備させる
        if game.dead_thread:
            await game.dead_thread.send(embed=discord.Embed(title=f"☀️ {game.day_count}日目：朝の結果発表", description="犠牲者を確認してください。", color=discord.Color.red()), silent=True)

        names = []
        for p in dead_list:
            if p in game.alive_players: 
                game.alive_players.remove(p)
            names.append(p.display_name)
            await channels.handle_player_death_vc(p, channel.guild)
        
        embed.description = f"❌ 昨夜の犠牲者: **{', '.join(names)}**"
        await target_channel.send(embed=embed, silent=True)
        if game.log_channel:
            await game.log_channel.send(embed=discord.Embed(description=f"❌ 昨夜の犠牲者: {', '.join(names)}", color=discord.Color.red()))
        
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
                await target_channel.send(embed=will_embed, silent=True)
                use_player_item(channel.guild.id, player_id)
                await asyncio.sleep(3) # 遺言1つにつき3秒追加
    else:
        if game.day_count == 1:
            # 0日目の朝は誰も死なないため、結果発表を省略して夜明けの通知のみにする
            await target_channel.send(embed=discord.Embed(description="☀️ 夜が明け、最初の朝が来ました。これより1日目の議論を開始します。", color=discord.Color.green()), silent=True)
        else:
            embed = discord.Embed(title=f"☀️ {game.day_count}日目：朝の結果発表", color=discord.Color.green())
            embed.description = "🛡️ 昨夜は誰も犠牲になりませんでした。"
            await target_channel.send(embed=embed, silent=True)
            if game.dead_thread:
                await game.dead_thread.send(embed=discord.Embed(description=f"☀️ {game.day_count}日目：朝は平穏でした。", color=discord.Color.green()), silent=True)

        if game.log_channel:
            await game.log_channel.send(embed=discord.Embed(description="🛡️ 犠牲者は出ませんでした。", color=discord.Color.green()))

    if await self.check_game_over(channel): 
        return

    await game.save_state(channel.guild) # 死亡処理と日付更新を保存
    
    # 0日目の朝だけは、結果発表の待ち時間を短縮（5秒）してテンポを上げる
    wait_time = 5 if game.day_count == 1 else game.morning_time
    await asyncio.sleep(wait_time)
    await self.start_discussion(channel)

# Discord.py の拡張ロードシステム用関数
async def setup(bot):
    pass
