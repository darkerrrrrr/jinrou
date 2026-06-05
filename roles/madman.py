# roles/madman.py
import discord
from roles.base import BaseRole

class Madman(BaseRole):
    name = "狂人"
    team = "人狼"  # 勝利条件は人狼陣営
    has_night_action = False