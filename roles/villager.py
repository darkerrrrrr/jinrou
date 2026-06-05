# roles/villager.py
import discord
from roles.base import BaseRole

class Villager(BaseRole):
    name = "村人"
    team = "村人"
    has_night_action = False