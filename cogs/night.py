import discord, asyncio
from config import game
from actions import ActionView
import channels

# アイテムシステム関連
from cogs.item import reset_items, ItemDrawView, get_player_item, use_player_item

async def start_night(self, channel):
    """夜フェーズを開始"""
    game.actions = {}
    
    # 毎晩の最初に、前夜に引いたアイテムデータをリセット（ただし怪盗の役職交換後のアイテムは保持）
    # 新しく村人だけがアイテムを引くので、既に持ってるアイテムはそのまま
    new_items = {}
    for player_id, item in player_items.items():
        # 死んだ人のアイテムは削除、生きてる人は保持
        if any(p.id == player_id for p in game.alive_players):
            new_items[player_id] = item
    player_items.clear()
    player_items.update(new_items)
    
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
            except Exception as e:
                print(f"⚠️ {player.display_name} ({role.name}) への能力通知DM失敗: {e}")
        elif role.name == "村人":
            # 普通の村人のみにアイテム支給ガチャボタンを送信
            try:
                await player.send("🎒 **【夜間の身支度】** 明日の過酷な議論に備え、手荷物を確認しましょう。下のボタンからアイテムを1つ獲得できます。", view=ItemDrawView())
            except Exception as e:
                print(f"⚠️ {player.display_name} へのアイテムガチャDM失敗: {e}")
                
    await asyncio.sleep(game.night_time)
    await process_night_results(self, channel)


async def process_night_results(self, channel):
    """夜の行動結果を処理"""
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
                    try:
                        await actor.send(f"🎭 【怪盗の強奪結果】: {target.display_name} から役職を奪いました！あなたの新しい役職は 【**{target_role.name}**】 です。")
                    except Exception as e:
                        print(f"⚠️ {actor.display_name} (怪盗) への結果通知DM失敗: {e}")
        game.thief_action_done = True

    # 【占い師の結果通知】
    for actor, data in game.actions.items():
        if data['action'] == "占い" and actor in game.alive_players:
            target = data['target']
            actual_role = game.roles.get(target)
            result_team = "人狼" if (actual_role and actual_role.name == "人狼") else "人間"
            try:
                await actor.send(f"🔮 【占い結果】: {target.display_name} を占いました。結果は 【**{result_team}**】 です。")
            except Exception as e:
                print(f"⚠️ {actor.display_name} (占い師) への占い結果通知DM失敗: {e}")

    # 【霊媒師の結果通知】
    for actor, data in game.actions.items():
        if data['action'] == "霊媒" and actor in game.alive_players:
            target = data['target']
            actual_role = game.roles.get(target)
            result_team = "人狼" if (actual_role and actual_role.name == "人狼") else "人間"
            try:
                await actor.send(f"👻 【霊媒結果】: {target.display_name} を霊視しました。正体は 【**{result_team}**】 です。")
            except Exception as e:
                print(f"⚠️ {actor.display_name} (霊媒師) への霊媒結果通知DM失敗: {e}")

    # 【襲撃対象の集計】
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

    # 【死亡判定】
    dead_list = []
    guarded_and_notified = set()
    for target in attacked_targets:
        if target in guarded_players:
            if target not in guarded_and_notified:
                await game.log_channel.send(f"🛡️ 狩人の護衛成功！ {target.display_name} への襲撃が阻止されました。")
                guarded_and_notified.add(target)
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

    # 【死亡者発表】
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
