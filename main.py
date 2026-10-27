import asyncio
import json
import logging
import os
import time
import datetime
import random

import discord
from discord.ext import commands
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MESSAGES_FILE = os.path.join(BASE_DIR, "messages.json")
STATS_FILE = os.path.join(BASE_DIR, "stats.json")
TEAM_FILE = os.path.join(BASE_DIR, "team.json")

load_dotenv(os.path.join(BASE_DIR, ".env"))
token = os.getenv('DISCORD_TOKEN')

handler = logging.FileHandler(
    filename=os.path.join(BASE_DIR, 'discord.log'), encoding='utf-8', mode='a'
)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

secret_role = "working"

#----BOT COMMANDS AND EVENTS----#

@bot.event
async def on_ready():
    print(f"We are ready to go in, {bot.user.name}")

@bot.event
async def on_member_join(member):
    await member.send(f"Welcome to the server, {member.name}!")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if "shit" in message.content.lower():
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        await message.channel.send(f"{message.author.mention}, please refrain from using inappropriate language.")

    session = sessions.get(message.author.id)
    if (
        session
        and message.guild is not None
        and session.phase == "working"
        and not session.paused
        and not message.content.startswith(bot.command_prefix)
        and get_user(message.author)["chatwatch"]
    ):
        now = time.monotonic()
        if now - session.last_callout > 90:
            session.last_callout = now
            session.chat_strikes += 1
            if session.chat_strikes % 3 == 0:
                session.slacked += 1
                session.nag_level += 1
                await message.channel.send(
                    f"{message.author.mention} Third chat strike. That counts as slacking now. Go work."
                )
                await session.notify_others()
            else:
                strike = ((session.chat_strikes - 1) % 3) + 1
                await message.channel.send(
                    f"{message.author.mention} I see you chatting during a focus block... ({strike}/3 strikes)"
                )

    await bot.process_commands(message)


@bot.command()
async def hello(ctx):
    await ctx.send(f"Hello, {ctx.author.mention}!")

@bot.command()
async def assign(ctx):
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    role = discord.utils.get(ctx.guild.roles, name = secret_role)
    if role is None:
        role = next((r for r in ctx.guild.roles if r.name.lower() == secret_role.lower()), None)

    if role:
        try:
            await ctx.author.add_roles(role)
            await ctx.send (f"{ctx.author.mention}, you have been assigned the '{secret_role}' role.")
        except discord.Forbidden:
            await ctx.send("I don't have permission to assign you that role.")

    else:
        await ctx.send(f"The role '{secret_role}' does not exist on this server.")

@bot.command()
async def remove(ctx):
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    role = discord.utils.get(ctx.guild.roles, name = secret_role)
    if role is None:
        role = next((r for r in ctx.guild.roles if r.name.lower() == secret_role.lower()), None)

    if role:
        try:
            await ctx.author.remove_roles(role)
            await ctx.send (f"{ctx.author.mention}, the '{secret_role}' role has been removed from you.")
        except discord.Forbidden:
            await ctx.send("I don't have permission to remove that role from you.")

    else:
        await ctx.send(f"The role '{secret_role}' does not exist on this server.")


@bot.command()
async def dm(ctx, *, msg):
    await ctx.author.send(f"You said: {msg}")

@bot.command()
async def reply(ctx):
    await ctx.reply(f"{ctx.author.mention}, this is a reply to your message.")

@bot.command()
async def poll(ctx, *, question: str = None):

    if question is None:
        await ctx.send("Please provide a question for the poll.")
        return
    
    embed = discord.Embed(title = "New Poll", description = question, color = discord.Color.blue())
    embed.set_footer(text = f"Poll created by {ctx.author.name}")
    
    poll_message = await ctx.send(embed=embed)
    await poll_message.add_reaction("👍")
    await poll_message.add_reaction("👎")

@bot.command()
@commands.has_role(secret_role)
async def secret(ctx):
    await ctx.send(f"Hello, {ctx.author.mention}! You have the secret role.")

@secret.error
async def secret_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send(f"Sorry, {ctx.author.mention}, you do not have the required role to use this command.")


#-----MESSAGES LOADED FROM JSON FILE-----#

DEFAULT_MESSAGES = {
    "checkin": [
        "Still focused?",
        "Quick check-in: are you working?",
        "Eyes on the task. How is it going?",
        "No distractions. Are you still working?",
        "Answer me: are you focused?",
    ],
    "on_yes": ["Good. Keep going!"],
    "on_no": [
        "Let's get back on track.",
        "Close the distraction and refocus.",
        "You know what you need to do. Get back to it.",
        "Enough slacking. Focus.",
        "Back to work. Now.",
    ],
    "on_ignored": [
        "No answer? I'm counting that as a distraction.",
        "I noticed you ignored me. Refocus.",
        "Silence is suspicious. Get back to work.",
        "Don't ignore the timer. Focus.",
        "I can wait, but your work can't.",
    ],

}

DEFAULT_TIPS = [
     "Put your phone in another room. Out of sight, out of mind.",
     "Write down the one thing you want finished by the end of this block.",
     "Close every tab you don't need right now.",
     "Drink some water before you start.",
     "Start with the ugliest, hardest part. It only gets easier.",
     "If a distracting thought pops up, jot it down and keep going.",   
    ]

PRESETS = {
    "sprint":(15,3),
    "classic": (25,5),
    "long": (50, 10),
    "deep": (90, 20),
}

MESSAGES = {}

def load_messages():
    global MESSAGES
    try:
        with open(MESSAGES_FILE, encoding="utf-8") as f:
            MESSAGES = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        MESSAGES = {key: list(values) for key, values in DEFAULT_MESSAGES.items()}

load_messages()

def pick(key: str, level: int) -> str:
    options = MESSAGES[key]
    return options[max(0, min(level, len(options) -1))]

# ----------------------------------------------------------------------------------------------------------------
# Notes:
# base_checkin: minutes between check-ins at level 0
# shrink: each nag level multiples that gap by this (smaller = faster)
# answer_secs: seconds you get to answer at level 0
#offset: added to the nag level when picking a message (drill starts angry)
#cap: highest message level this mode can reach
#----------------------------------------------------------------------------------------------------------------

MODES = {
    "gentle":{
        "base_checkin":8, "shrink":0.85, "answer_secs": 90, "offset":0, "cap": 2
    },

    "normal":{
        "base_checkin":5, "shrink":0.60, "answer_secs": 60, "offset":0, "cap": 4
    },

    "drill":{
        "base_checkin":3, "shrink":0.50, "answer_secs": 40, "offset":2, "cap": 4
    },
}

MIN_CHECKIN_MINUTES = 0.5
MIN_ANSWER_SECONDS = 15
SNOOZE_MINUTES = 5
SNOOZES_PER_BLOCK = 2
PAUSE_LIMIT_SECONDS = 600

# Stats + settings

def load_stats() -> dict:
    try:
        with open(STATS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_stats():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(STATS, f, indent=2)

STATS = load_stats()

def load_team() -> dict:
    try:
        with open(TEAM_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_team():
    with open(TEAM_FILE, "w", encoding="utf-8") as f:
        json.dump(TEAM, f, indent=2)

TEAM = load_team()

def add_team_minutes(guild_id: int, minutes:float) -> bool:
    """Add minutes to the server goal. Returns True if this block pushed it over the goal."""
    t = TEAM.get(str(guild_id))
    if not t or t["goal"] <= 0:
        return False

    before = t["progress"]
    t["progress"] += minutes
    save_team()
    return before < t["goal"] <= t["progress"]


def get_user(user: discord.abc.User) -> dict:
    entry = STATS.setdefault(str(user.id), {})
    entry["name"] = user.display_name
    entry.setdefault("mode", "normal")
    entry.setdefault("dm", False)
    entry.setdefault("blocks", 0)
    entry.setdefault("clean", 0)
    entry.setdefault("streak", 0)
    entry.setdefault("best_streak", 0)
    entry.setdefault("slacks", 0)
    entry.setdefault("minutes", 0)
    entry.setdefault("goal", 4)
    entry.setdefault("today_date", "")
    entry.setdefault("today_blocks", 0)
    entry.setdefault("buddy", None)
    entry.setdefault("shame", False)
    entry.setdefault("hardcore", False)
    entry.setdefault("week_key", "")
    entry.setdefault("week_minutes", 0)
    entry.setdefault("badges", [])
    entry.setdefault("history", [])
    entry.setdefault("todos", [])
    entry.setdefault("chatwatch", False)
    entry.setdefault("last_day", "")
    entry.setdefault("day_streak", 0)
    entry.setdefault("best_day_streak", 0)
    entry.setdefault("moods", [])
    entry.setdefault("moodcheck", True)
    return entry

RANKS = [
    (0, "Distracted Rookie"),
    (60, "Warming Up"),
    (300, "Focused Apprentice"),
    (1000, "Lock-In Specialist"),
    (3000, "Deep Work Master"),
    (6000, "Pomodoro Legend"),
]

def get_rank(minutes: float) -> str:
    title = RANKS[0][1]
    for threshold, name in RANKS:
        if minutes >= threshold:
            title = name
    return title

BADGE_INFO = {
    "first": "First Pomodoro",
    "hat_trick": "Hat Trick: 3 clean blocks in a row",
    "unstoppable": "Unstoppable: 10 clean blocks in a row",
    "marathon": "Marathoner: a clean block of 50+ minutes",
    "night_owl": "Night Owl: finished a block between midnight and 5am",
    "goal_getter": "Goal Getter: hit your daily goal",
    "hardcore": "Hardcore: finished a clean block in hardcore mode",
    "week_warrior": "Week warrior: 7 days in a row."
}

def award_badges(s: dict, minutes: float, slacks: int, hardcore: bool, hour: int, task: str = "") -> list:
    have = s.setdefault("badges", [])
    earned: list[str] = []

    def give(key):
        if key not in have:
            have.append(key)
            earned.append(key)

    give("first")
    if s.get("streak", 0) >= 3:
        give("hat_trick")
    if s.get("streak", 0) >= 10:
        give("unstoppable")
    if minutes >= 50 and slacks == 0:
        give("marathon")
    if 0 <= hour < 5:
        give("night_owl")
    if s.get("goal", 0) and s.get("today_blocks", 0) >= s["goal"]:
        give("goal_getter")
    if hardcore and slacks == 0:
        give("hardcore")
    if s.get("day_streak", 0) >= 7:
        give("week_warrior")
    return earned


def current_day_streak(s: dict) -> int:
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    if s["last_day"] in (today.isoformat(), yesterday.isoformat()):
        return s["day_streak"]
    return 0


def record_block(user, minutes: float, slacks: int, task: str = "", hardcore: bool = False):
    s = get_user(user)
    now = datetime.datetime.now()
    today = now.date().isoformat()

    if s["last_day"] != today:
        s["day_streak"] = s["day_streak"] + 1 if s["last_day"] == (now.date() - datetime.timedelta(days=1)).isoformat() else 1
        s["last_day"] = today
        s["best_day_streak"] = max(s["best_day_streak"], s["day_streak"])

    if s["today_date"] != today:
        s["today_date"] = today
        s["today_blocks"] = 0
    s["today_blocks"] += 1

    if s["week_key"] != f"{now.isocalendar()[0]} - W{now.isocalendar()[1]:02d}":
        s["week_key"] = f"{now.isocalendar()[0]} - W{now.isocalendar()[1]:02d}"
        s["week_minutes"] = 0
    s["week_minutes"] += minutes

    s["blocks"] += 1
    s["minutes"] += minutes
    s["slacks"] += slacks
    if slacks == 0:
        s["clean"] += 1
        s["streak"] += 1
        s["best_streak"] = max(s["best_streak"], s["streak"])
    else:
        s["streak"] = 0

    s["history"].append({"date": today, "task": (task or "")[:60], "minutes": minutes, "slacks": slacks})
    s["history"] = s["history"][-10:]

    earned = award_badges(s, minutes, slacks, hardcore, now.hour, task)
    save_stats()
    return s, earned

# Check-in buttons

class CheckInView(discord.ui.View):
    """Yes / No/ Snooze buttons. Only the person with the timer can press them."""

    def __init__(self, user_id: int, timeout: float, can_snooze: bool):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.answer = None
        if not can_snooze:
            self.remove_item(self.snooze)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("You are not the owner of this timer.", ephemeral=True)
            return False
        return True

    async def _finish(self, interaction: discord.Interaction, answer: str):
        self.answer = answer
        await interaction.response.edit_message(view=None)
        self.stop()

    @discord.ui.button(label= "Yes", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._finish(interaction, "yes")

    @discord.ui.button(label= "No", style=discord.ButtonStyle.danger)
    async def no(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._finish(interaction, "no")

    @discord.ui.button(label = f"Snooze {SNOOZE_MINUTES} min", style=discord.ButtonStyle.secondary)
    async def snooze(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._finish(interaction, "snooze")

MOOD_FACES = {1: "😫", 2: "😕", 3: "😐", 4: "🙂", 5: "🤩"}
MOOD_REPLIES = {
    1: "Rough one. Tiny wins count. Take a real break.",
    2: "Not your best, but you showed up. That matters.",
    3: "Solid, steady work. Not every block needs to be a masterpiece.",
    4: "Nice. That's the good stuff.",
    5: "Flow state unlocked! 🔥 Remember what made this one work.",
}

SPARKS = "▁▃▅▆█"
TIME_BUCKETS = [
    ("Morning", range(5, 12)),
    ("Afternoon", range(12, 17)),
    ("Evening", range(17, 22)),
    ("Night", [22, 23, 0, 1, 2, 3, 4]),
]

background_tasks = set()


class MoodView(discord.ui.View):
    """1 to 5 mood buttons. Only the person who finished the block can press them."""

    def __init__(self, user, minutes: float, slacks: int, task: str):
        super().__init__(timeout=120)
        self.user = user
        self.minutes = minutes
        self.slacks = slacks
        self.task = task
        self.message = None
        self.answered = False

        for rating, face in MOOD_FACES.items():
            button = discord.ui.Button(label=str(rating), emoji=face, style=discord.ButtonStyle.secondary)
            button.callback = self._make_callback(rating)
            self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This mood check isn't yours.", ephemeral=True)
            return False
        return True

    def _make_callback(self, rating: int):
        async def callback(interaction: discord.Interaction):
            now = datetime.datetime.now()
            s = get_user(self.user)
            s["moods"].append({
                "date": now.date().isoformat(),
                "hour": now.hour,
                "rating": rating,
                "task": self.task[:40],
                "minutes": self.minutes,
                "slacks": self.slacks,
            })
            s["moods"] = s["moods"][-50:]
            save_stats()

            reply = MOOD_REPLIES[rating]
            if rating >= 4 and self.slacks >= 2:
                reply += " (Though I did catch you slacking a few times. 😏)"
            elif rating <= 2 and self.slacks == 0:
                reply += " You stayed focused even while feeling rough. Respect."

            self.answered = True
            await interaction.response.edit_message(
                content=f"{self.user.mention} Logged {MOOD_FACES[rating]} **{rating}/5**. {reply}",
                view=None,
            )
            self.stop()
        return callback

    async def on_timeout(self):
        if not self.answered and self.message is not None:
            try:
                await self.message.edit(content=f"{self.user.mention} Mood check skipped. No worries.", view=None)
            except discord.HTTPException:
                pass

#Pomodoro Session

sessions: dict[int, "PomodoroSession"] = {}

class PomodoroSession:
    def __init__(self, ctx, work_min: float, break_min: float, task: str):
        self.user = ctx.author
        self.channel = ctx.channel
        self.work_min = work_min
        self.break_min = break_min
        self.task = task
        settings = get_user(self.user)
        self.hardcore = settings["hardcore"]
        self.paused = False
        self.paused_at = 0.0
        self.pause_used = False
        self.next_checkin_at = 0.0
        self.checking_in = False
        self.buddy_pinged = False

        self.mode_name = settings["mode"] if settings["mode"] in MODES else "normal"
        self.mode = MODES[self.mode_name]
        self.dest = self.user if settings["dm"] else self.channel

        self.phase = "starting"
        self.phase_ends_at = time.monotonic()
        self.nag_level = 0
        self.slacked = 0
        self.snoozes_left = SNOOZES_PER_BLOCK
        self.reset_used = False
        self.cycles_done = 0
        self.runner = None
        self.skip_event = asyncio.Event()
        self.halftime_sent = False
        self.fivemin_sent = False
        self.chat_strikes = 0
        self.last_callout = 0.0

    # helpers
    async def say(self, content: str, **kwargs):
        """Send to the DM or channel. Falls back to the channel if DMs are closed."""
        try:
            return await self.dest.send(content, **kwargs)
        except discord.Forbidden:
            self.dest = self.channel
            return await self.channel.send(
                f"{self.user.mention} (I couldn't DM you, so I'll nag you here.)\n{content}", **kwargs
            )

    def start_mood_check(self, minutes: float, slacks: int, task: str):
        """Send the mood prompt in the background so it never delays your break."""
        bg = asyncio.create_task(self._mood_prompt(minutes, slacks, task))
        background_tasks.add(bg)
        bg.add_done_callback(background_tasks.discard)

    async def _mood_prompt(self, minutes: float, slacks: int, task: str):
        try:
            view = MoodView(self.user, minutes, slacks, task)
            view.message = await self.say(
                f"{self.user.mention} Quick mood check (optional): how focused did that block *feel*?",
                view=view,
            )
        except discord.HTTPException:
            pass


    def time_left(self) -> float:
        ref = self.paused_at if self.paused else time.monotonic()
        return max(0, self.phase_ends_at - ref)

    def resume(self):
        gap = time.monotonic() - self.paused_at
        self.phase_ends_at += gap
        self.next_checkin_at += gap
        self.paused = False

    async def notify_others(self):
        """Ping the buddy and/or post to the wall of shame. (server channels only)"""
        if getattr(self.channel, "guild", None) is None:
            return
        s = get_user(self.user)
        if s["buddy"] and not self.buddy_pinged:
            self.buddy_pinged = True
            await self.channel.send(
                f"<@{s['buddy']}> heads up: {self.user.display_name} just got caught slacking. "
                "Send some motivation (or judgment)."
            )

        if s["shame"] and self.slacked == 3:
            await self.channel.send(
                f"**WALL OF SHAME** {self.user.mention} has been caught slacking 3 times "
                "in one block. Point and stare."
            )

    async def set_role(self, give: bool):
        """Give or remove the 'working' role. Does nothing in DMs or if the role is missing."""
        guild = getattr(self.channel, "guild", None)
        if guild is None or not isinstance(self.user, discord.Member):
            return
        role = discord.utils.get(guild.roles, name=secret_role)
        if role is None:
            return
        try:
            if give:
                await self.user.add_roles(role)
            else:
                await self.user.remove_roles(role)
        except discord.Forbidden:
            pass


    def msg_level(self) -> int:
        return max(0, min(self.nag_level + self.mode["offset"], self.mode["cap"]))
        
    def checkin_delay_seconds(self) -> float:
        delay_minutes = self.mode["base_checkin"] * self.mode["shrink"] ** self.nag_level
        return max(MIN_CHECKIN_MINUTES, delay_minutes) * 60

    def answer_timeout_seconds(self) -> float:
        return max(MIN_ANSWER_SECONDS, self.mode["answer_secs"] - self.nag_level * 10)

    # main loop

    async def run(self):
        try:
            while True:
                await self.work_phase()
                await self.break_phase()
        finally:
            sessions.pop(self.user.id, None)
            await self.set_role(False)

    async def work_phase(self):
        self.phase = "working"
        self.nag_level = 0
        self.slacked = 0
        self.snoozes_left = 0 if self.hardcore else SNOOZES_PER_BLOCK
        self.reset_used = False
        self.pause_used = False
        self.paused = False
        self.buddy_pinged = False
        self.halftime_sent = False
        self.fivemin_sent = False
        self.chat_strikes = 0
        self.phase_ends_at = time.monotonic() + self.work_min * 60
        self.next_checkin_at = time.monotonic() + self.checkin_delay_seconds()

        await self.set_role(True)
        tag = " **HARDCORE**" if self.hardcore else ""
        await self.say(f"{random.choice(MESSAGES.get('tips', DEFAULT_TIPS))}")
        await self.say(
            f"{self.user.mention} Focus time! **{self.work_min:g} min** on: **{self.task}**."
            f" Mode: **{self.mode_name}**.{tag} I'll check in on you. >:D"
        )

        while self.paused or time.monotonic() < self.phase_ends_at:
            await asyncio.sleep(1)

            if self.paused:
                if time.monotonic() - self.paused_at > PAUSE_LIMIT_SECONDS:
                    self.resume()
                    await self.say(f"{self.user.mention} Pause is over. Back to work!")
                continue

            left = self.phase_ends_at - time.monotonic()
            total = self.work_min * 60
            if not self.halftime_sent and total >= 600 and left <= total / 2:
                self.halftime_sent = True
                await self.say(f"{self.user.mention} Halfway there! Keep that momentum going.")
            if not self.fivemin_sent and total >= 900 and left <= 300:
                self.fivemin_sent = True
                await self.say(f"{self.user.mention} 5 minutes left. Finish strong!")

            if time.monotonic() >= self.next_checkin_at and self.next_checkin_at < self.phase_ends_at:
                override = await self.check_in()
                delay = override if override is not None else self.checkin_delay_seconds()
                self.next_checkin_at = time.monotonic() + delay

        self.cycles_done += 1
        old_rank = get_rank(get_user(self.user)["minutes"])
        stats, earned = record_block(self.user, self.work_min, self.slacked, self.task, self.hardcore)
        new_rank = get_rank(stats["minutes"])

        if self.slacked == 0:
            summary = f"Zero slacking. Respect. Good streak: **{stats['streak']}**."
        else:
            summary = f"I caught you slacking **{self.slacked}** time(s) this round. Streak reset."

        goal_line = ""
        if stats["goal"] > 0:
            if stats["today_blocks"] == stats["goal"]:
                goal_line = f" Daily goal reached ({stats['goal']}/{stats['goal']})!"
            else:
                goal_line = f" Today: **{stats['today_blocks']}/{stats['goal']}**."

        rank_line = f"\n Rank up! You are now a **{new_rank}**." if new_rank != old_rank else ""
        badge_line = "".join(f"\n New badge: **{BADGE_INFO[k]}**" for k in earned)
        guild = getattr(self.channel, "guild", None)
        if guild is not None and add_team_minutes(guild.id, self.work_min):
            team_line = "\n **TEAM GOAL REACHED!** Everyone in this server did that together."
        else:
            team_line = ""

        await self.say(
            f"{self.user.mention} Work block done! {summary}{goal_line}{rank_line}{badge_line}{team_line}"
        )

        if get_user(self.user)["moodcheck"]:
            self.start_mood_check(self.work_min, self.slacked, self.task)

    async def check_in(self):
        """Ask if user is working and return a custom delay for the next check-in."""
        self.checking_in = True
        try:
            view = CheckInView(
                self.user.id,
                timeout=self.answer_timeout_seconds(),
                can_snooze=self.snoozes_left > 0,
            )
            msg = await self.say(
                f"{self.user.mention} {pick('checkin', self.msg_level())}", view=view
            )
            await view.wait()

            if view.answer == "yes":
                await self.say(pick("on_yes", self.msg_level()))
                self.nag_level = max(0, self.nag_level - 1)
                return None

            if view.answer == "snooze":
                self.snoozes_left -= 1
                await self.say(
                    f"Fine...{SNOOZE_MINUTES} more minutes. "
                    f"({self.snoozes_left} snooze(s) left this block.)"
                )
                return SNOOZE_MINUTES * 60

            if view.answer is None:
                try:
                    await msg.edit(view=None)
                except discord.HTTPException:
                    pass
                nag = pick("on_ignored", self.msg_level())
            else:
                nag = pick("on_no", self.msg_level())

            self.slacked += 1
            self.nag_level += 1
            await self.say(f"{self.user.mention} {nag}")
            await self.notify_others()
            return None

        finally:
            self.checking_in = False

    async def break_phase(self):
        self.phase = "break"
        long_break = self.cycles_done % 4 == 0
        minutes = self.break_min * 3 if long_break else self.break_min
        self.phase_ends_at = time.monotonic() + minutes * 60
        self.skip_event.clear()
        await self.set_role(False)

        label = "**Long break!** You earned it." if long_break else "Break time!"
        await self.say(
            f"{self.user.mention} {label} **{minutes:g} min**. Stretch, drink water, "
            "and do NOT open Youtube, Tiktok, or anything brainrotting"
        )

        try:
            await asyncio.wait_for(self.skip_event.wait(), timeout=minutes * 60)
            await self.say(f"{self.user.mention} Break skipped. Okay, someone's motivated. Back to it!")
        except asyncio.TimeoutError:
            await self.say(f"{self.user.mention} Break's over, back to it!")


# Pomodoro commands

@bot.command(name="pomodoro", aliases=["pomo"])
async def pomodoro(ctx, work: float = 25, rest: float = 5, *, task: str = "your work"):
    if work <= 0 or rest < 0:
        await ctx.send("Pomodoro times must be positive numbers.")
        return

    if ctx.author.id in sessions:
        await ctx.send("You already have a timer running! Use '!stop' first.")
        return

    task = task.strip()
    if not task:
        task = "your work"
    if task.startswith("#") and task[1:].isdigit():
        todos = get_user(ctx.author)["todos"]
        index = int(task[1:]) - 1
        if not 0 <= index < len(todos):
            await ctx.send("I couldn't find that to-do number. Check '!todo'.")
            return
        task = todos[index]

    await ctx.send("Starting your timer....")
    session = PomodoroSession(ctx, work, rest, task)
    session.runner = asyncio.create_task(session.run())
    sessions[ctx.author.id] = session


@pomodoro.error
async def pomodoro_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send("Usage: '!pomodoro [work_minutes] [break_minutes] [task]' (minutes must be numbers)")
    else:
        raise error


@bot.command()
async def stop(ctx):
    session = sessions.get(ctx.author.id)
    if not session:
        await ctx.send("You don't have a timer running.")
        return

    penalty = ""
    if session.hardcore and session.phase == "working":
        s = get_user(ctx.author)
        s["streak"] = 0
        save_stats()
        penalty = " You quit mid-block in hardcore mode, so your streak is reset."

    if session.runner is not None and not session.runner.done():
        session.runner.cancel()
    sessions.pop(ctx.author.id, None)
    await ctx.send(f"Timer stopped. You finished **{session.cycles_done}** pomodoro(s).{penalty} Come back soon!")


@bot.command()
async def status(ctx):
    session = sessions.get(ctx.author.id)
    if not session:
        await ctx.send("You don't have a timer running. Start one with '!pomodoro'.")
        return

    remaining = session.time_left()
    paused_note = " PAUSED" if session.paused else ""
    mins, secs = divmod(int(remaining), 60)
    await ctx.send(
        f"{ctx.author.mention} Phase **{session.phase}** | Time left: **{mins}m {secs}s**{paused_note} | "        f"Pomodoros done: **{session.cycles_done}** | Nag level: **{session.nag_level}** | "
        f"Mode: **{session.mode_name}**"
    )


@bot.command(name="resetnag")
async def resetnag(ctx):
    """Calm the bot down once per work block."""
    session = sessions.get(ctx.author.id)
    if not session or session.phase != "working":
        await ctx.send("There's no work block running to reset.")
        return

    if session.hardcore:
        await ctx.send("No resets in hardcore mode.")
        return

    if session.reset_used:
        await ctx.send("You already used your reset this block. Earn your peace the hard way...")
        return

    session.reset_used = True
    session.nag_level = 0
    await ctx.send("Nag level reset to 0. One per block so don't waste it.")


@bot.command(name="pause")
async def pause(ctx):
    session = sessions.get(ctx.author.id)
    if not session or session.phase != "working":
        await ctx.send("There's no work block running to pause.")
        return
    if session.hardcore:
        await ctx.send("No pausing in hardcore mode.")
        return
    if session.paused:
        await ctx.send("You're already paused. Use '!resume'.")
        return
    if getattr(session, "pause_used", False):
        await ctx.send("You already used your pause this block.")
        return
    if session.checking_in:
        await ctx.send("Answer my check-in first, then pause.")
        return
    session.paused = True
    session.pause_used = True
    session.paused_at = time.monotonic()
    await ctx.send(f"Paused for up to {PAUSE_LIMIT_SECONDS // 60} min. Use '!resume' when you're back.")


@bot.command(name="resume")
async def resume(ctx):
    session = sessions.get(ctx.author.id)
    if not session or not session.paused:
        await ctx.send("You're not paused.")
        return
    session.resume()
    await ctx.send("Back to work! The clock is running again.")


@bot.command(name="hardcore")
async def hardcore(ctx, setting: str = None):
    """!hardcore on|off"""
    s = get_user(ctx.author)
    if setting is None or setting.lower() not in ("on", "off"):
        await ctx.send(
            f"Hardcore is **{'on' if s['hardcore'] else 'off'}**. Use '!hardcore on' or '!hardcore off'.\n"
            "Hardcore rules: no snooze, no pause, no '!resetnag', and using '!stop' mid-block resets your streak."
        )
        return
    s["hardcore"] = setting.lower() == "on"
    save_stats()
    note = " (applies to your next pomodoro.)" if ctx.author.id in sessions else ""
    await ctx.send(f"Hardcore mode **{'on' if s['hardcore'] else 'off'}**.{note}")


@bot.command(name="buddy")
async def buddy(ctx, member: discord.Member = None):
    """!buddy @friend: they get pinged when you get caught slacking."""
    s = get_user(ctx.author)
    if member is None:
        if s["buddy"]:
            await ctx.send(f"Your buddy is <@{s['buddy']}>. Remove them with '!unbuddy'.")
        else:
            await ctx.send("Pick a buddy with '!buddy @friend'.")
        return
    if member.bot or member.id == ctx.author.id:
        await ctx.send("Pick a real person who isn't you")
        return
    s["buddy"] = member.id
    save_stats()
    await ctx.send(f"{member.mention} is now {ctx.author.display_name}'s accountability buddy. Good luck.")


@buddy.error
async def buddy_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send("I couldn't find that person. Mention them like '!buddy @friend' (server channels only).")
    else:
        raise error


@bot.command(name="unbuddy")
async def unbuddy(ctx):
    s = get_user(ctx.author)
    s["buddy"] = None
    save_stats()
    await ctx.send("Buddy removed. You're on your own now.")


@bot.command(name="shamewall")
async def shamewall(ctx, setting: str = None):
    """!shamewall on|off: opt in to being publicly called out after 3 slacks in one block."""
    s = get_user(ctx.author)
    if setting is None or setting.lower() not in ("on", "off"):
        await ctx.send(f"Wall of shame is **{'on' if s['shame'] else 'off'}**. Use '!shamewall on' or '!shamewall off'.")
        return
    s["shame"] = setting.lower() == "on"
    save_stats()
    await ctx.send(f"Wall of shame **{'on' if s['shame'] else 'off'}**.")


@bot.command(name="weekly")
async def weekly(ctx):
    iso = datetime.date.today().isocalendar()
    week = f"{iso[0]} - W{iso[1]:02d}"
    players = [s for s in STATS.values() if s.get("week_key") == week and s.get("week_minutes", 0) > 0]
    if not players:
        await ctx.send("Nobody has focused this week yet.")
        return

    players.sort(key=lambda s: s["week_minutes"], reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, s in enumerate(players[:10]):
        rank = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{rank} **{s['name']}**: {s['week_minutes']:.0f} min this week")
    await ctx.send(embed=discord.Embed(title="This week's focus", description="\n".join(lines), color=discord.Color.purple()))


@bot.command(name="badges")
async def badges(ctx):
    s = get_user(ctx.author)
    lines = [
        f"✅ {label}" if key in s["badges"] else f"🔒 {label}"
        for key, label in BADGE_INFO.items()
    ]
    await ctx.send(embed=discord.Embed(title=f"{ctx.author.display_name}'s badges", description="\n".join(lines), color=discord.Color.orange()))


@bot.command(name="history")
async def history(ctx):
    s = get_user(ctx.author)
    if not s["history"]:
        await ctx.send("No finished pomodoros yet. Go do one.")
        return
    lines = [
        f"`{h['date']}` **{h['task']}**: {h['minutes']:g} min, {h['slacks']} slack(s)"
        for h in reversed(s["history"])
    ]
    await ctx.send(embed=discord.Embed(title="Your last sessions", description="\n".join(lines), color=discord.Color.teal()))


@bot.command(name="hype")
async def hype(ctx):
    await ctx.send(f"{ctx.author.mention} {random.choice(MESSAGES.get('on_yes', DEFAULT_MESSAGES['on_yes']))}")


@bot.command(name="roastme")
async def roastme(ctx):
    await ctx.send(f"{ctx.author.mention} {random.choice(MESSAGES.get('on_no', DEFAULT_MESSAGES['on_no']))}")


@bot.command(name="extend")
async def extend(ctx, minutes: float = 5):
    """!extend [minutes]: add time to your current work block."""
    session = sessions.get(ctx.author.id)
    if not session or session.phase != "working":
        await ctx.send("There's no work block running to extend.")
        return

    if minutes <= 0 or minutes > 60:
        await ctx.send("Pick an extension between 0 and 60 minutes")
        return

    session.phase_ends_at += minutes * 60
    session.work_min += minutes
    await ctx.send(f"Added **{minutes:g} min** to your block. Look at you, getting into the zone")


@bot.command(name="skipbreak")
async def skipbreak(ctx):
    session = sessions.get(ctx.author.id)
    if not session or session.phase != "break":
        await ctx.send("You're not on a break right now.")
        return
    session.skip_event.set()


@bot.command(name="goal")
async def goal(ctx, blocks: int = None):
    """!goal [pomodoros_per_day]: set or view your daily goal. 0 turns it off."""
    s = get_user(ctx.author)
    today = datetime.date.today().isoformat()
    done = s["today_blocks"] if s["today_date"] == today else 0

    if blocks is None:
        await ctx.send(f"Daily goal: **{s['goal']}** | Done today: **{done}**. Change it with '!goal 6'.")
        return

    if not 0 <= blocks <= 20:
        await ctx.send("Pick a goal between 0 and 20 (0 turns it off).")
        return

    s["goal"] = blocks
    save_stats()
    await ctx.send(f"Daily goal set to **{blocks}** pomodoro(s). Done today: **{done}**.")


@goal.error
async def goal_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send("Usage: '!goal 4' (a whole number)")
    else:
        raise error


# Settings

@bot.command(name="nagmode")
async def nagmode(ctx, mode: str = None):
    """!nagmode gentle|normal|drill"""
    s = get_user(ctx.author)
    if mode is None or mode.lower() not in MODES:
        await ctx.send(
            f"Your mode is **{s['mode']}**. Choose one: '!nagmode gentle', '!nagmode normal', '!nagmode drill'.\n"
            "**gentle**: slow, mostly encouraging\n"
            "**normal** escalates quickly\n"
            "**drill**: starts angry, checks in constantly >:D"
        )
        return
    s["mode"] = mode.lower()
    save_stats()
    note = " (applies to your next pomodoro.)" if ctx.author.id in sessions else ""
    await ctx.send(f"Nag mode set to **{s['mode']}**.{note}")


@bot.command(name="dmmode")
async def dmmode(ctx, setting: str = None):
    """!dmmode on|off"""
    s = get_user(ctx.author)
    if setting is None or setting.lower() not in ("on", "off"):
        await ctx.send(f"DM mode is **{'on' if s['dm'] else 'off'}**. Use '!dmmode on' or '!dmmode off'.")
        return
    s["dm"] = setting.lower() == "on"
    save_stats()
    note = " (applies to your next pomodoro)" if ctx.author.id in sessions else ""
    await ctx.send(
        f"DM mode **{'on' if s['dm'] else 'off'}**."
        f"{'I will nag you privately.' if s['dm'] else 'I will nag you in the channel.'}{note}"
    )


# stats + leaderboard

@bot.command(name="mystats")
async def mystats(ctx):
    s = get_user(ctx.author)
    embed = discord.Embed(title=f"{ctx.author.display_name}'s focus stats", color=discord.Color.green())
    embed.add_field(name="Pomodoros", value=str(s["blocks"]))
    embed.add_field(name="Clean blocks", value=str(s["clean"]))
    embed.add_field(name="Current streak", value=str(s["streak"]))
    embed.add_field(name="Best streak", value=str(s["best_streak"]))
    embed.add_field(name="Times caught slacking", value=str(s["slacks"]))
    embed.add_field(name="Focus minutes", value=f"{s['minutes']:.0f}")
    embed.add_field(name="Day streak", value=f"{current_day_streak(s)} (best {s['best_day_streak']})")
    embed.add_field(name="Rank", value=get_rank(s["minutes"]))
    today = datetime.date.today().isoformat()
    done = s["today_blocks"] if s["today_date"] == today else 0
    embed.add_field(name="Today", value=f"{done}/{s['goal']}")
    await ctx.send(embed=embed)


@bot.command(name="leaderboard", aliases=["lb"])
async def leaderboard(ctx):
    players = [s for s in STATS.values() if s.get("blocks", 0) > 0]
    if not players:
        await ctx.send("Nobody has finished a pomodoro yet. Be the first!")
        return

    players.sort(key=lambda s: (s["best_streak"], s["clean"], s["minutes"]), reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, s in enumerate(players[:10]):
        rank = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{rank} **{s['name']}**: best streak {s['best_streak']} | {s['clean']} clean | {s['minutes']:.0f} min")
    embed = discord.Embed(title="Most focused", description="\n".join(lines), color=discord.Color.gold())
    await ctx.send(embed=embed)


@bot.command(name="preset")
async def preset(ctx, name: str = None, *, task: str = "your work"):
    if name is None or name.lower() not in PRESETS:
        lines = [f"**{k}**: {w} work min / {b} min break" for k, (w, b) in PRESETS.items()]
        await ctx.send("Pick a preset, like '!preset classic your essay':\n" + "\n".join(lines))
        return
    work, rest = PRESETS[name.lower()]
    await ctx.invoke(pomodoro, work=work, rest=rest, task=task)


@bot.group(name="todo", invoke_without_command=True)
async def todo(ctx):
    s = get_user(ctx.author)
    if not s["todos"]:
        await ctx.send("Your to-do list is empty. Add one with '!todo add write essay'.")
        return

    lines = [f"**{i}.** {t}" for i, t in enumerate(s["todos"], 1)]
    embed = discord.Embed(title=f"{ctx.author.display_name}'s to-do list", description="\n".join(lines), color=discord.Color.blurple())
    embed.set_footer(text="Start one with '!pomodoro 25 5 #1'")
    await ctx.send(embed=embed)


@todo.command(name="add")
async def todo_add(ctx, *, text: str):
    s = get_user(ctx.author)
    if len(s["todos"]) >= 15:
        await ctx.send("15 items max. Finish something first!")
        return
    s["todos"].append(text[:80])
    save_stats()
    await ctx.send(f"Added as **#{len(s['todos'])}**.")


@todo.command(name="done")
async def todo_done(ctx, number: int):
    s = get_user(ctx.author)
    if not 1 <= number <= len(s["todos"]):
        await ctx.send("That number isn't on your list.")
        return
    finished = s["todos"].pop(number - 1)
    save_stats()
    await ctx.send(f"Crossed off: **{finished}**. Nice.")


@bot.command(name="chatwatch")
async def chatwatch(ctx, setting: str = None):
    """!chatwatch on|off: get called out if you chat during a work block."""
    s = get_user(ctx.author)
    if setting is None or setting.lower() not in ("on", "off"):
        await ctx.send(
            f"Chat watch is **{'on' if s['chatwatch'] else 'off'}**. Use '!chatwatch on' or '!chatwatch off'.\n"
            "When on, chatting during a work block earns a strike, and every 3rd strike counts as slacking."
        )
        return

    s["chatwatch"] = setting.lower() == "on"
    save_stats()
    await ctx.send(f"Chat watch **{'on' if s['chatwatch'] else 'off'}**.")


@bot.command(name="teamgoal")
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def teamgoal(ctx, hours: float):
    """!teamgoal <hours>: set a shared focus goal for the server (admins only). 0 turns it off."""
    if not 0 <= hours <= 1000:
        await ctx.send("Pick a goal between 0 and 1000 hours.")
        return
    TEAM[str(ctx.guild.id)] = {"goal": hours * 60, "progress": 0.0}
    save_team()
    if hours == 0:
        await ctx.send("Team goal turned off.")
    else:
        await ctx.send(f"Team goal set: **{hours:g} hours** of focus, starting from zero.")


@bot.command(name="team")
@commands.guild_only()
async def team(ctx):
    t = TEAM.get(str(ctx.guild.id))
    if not t or t["goal"] <= 0:
        await ctx.send("No team goal yet. An admin can set one with '!teamgoal 20' (hours).")
        return

    ratio = min(1.0, t["progress"] / t["goal"])
    filled = int(ratio * 20)
    bar = "█" * filled + "░" * (20 - filled)
    await ctx.send(
        f"**Team focus goal**\n{bar} {ratio * 100:.0f}%\n"
        f"{t['progress'] / 60:.1f} / {t['goal'] / 60:.1f} hours"
    )


@bot.event
async def on_command_error(ctx, error):
    if ctx.command and ctx.command.has_error_handler():
        return
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"You're missing '{error.param.name}'. Try '!nagshelp' for usage.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("One of those arguments doesn't't look right. Try '!nagshelp' for usage.")
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.send("That command only works in a server.")
    elif isinstance(error, (commands.MissingPermissions, commands.NotOwner)):
        await ctx.send("You don't have permission to do that.")
    else:
        raise error

@bot.command(name="mood")
async def mood(ctx, setting: str = None):
    """!mood on|off: turn the after-block mood check on or off."""
    s = get_user(ctx.author)
    if setting is None or setting.lower() not in ("on", "off"):
        await ctx.send(
            f"Mood check-ins are **{'on' if s['moodcheck'] else 'off'}**. Use '!mood on' or '!mood off'.\n"
            "See your trends with '!moodchart'."
        )
        return
    s["moodcheck"] = setting.lower() == "on"
    save_stats()
    await ctx.send(f"Mood check-ins **{'on' if s['moodcheck'] else 'off'}**.")

@bot.command(name="moodchart", aliases=["moods"])
async def moodchart(ctx):
    s = get_user(ctx.author)
    moods = s["moods"]
    if not moods:
        await ctx.send("No mood check-ins yet. Finish a pomodoro and tap a face!")
        return

    def avg(items):
        return sum(m["rating"] for m in items) / len(items)

    spark = "".join(SPARKS[m["rating"] - 1] for m in moods[-30:])
    lines = []
    for m in moods[-15:]:
        bar = "█" * m["rating"] + "░" * (5 - m["rating"])
        task = m["task"].replace("`", "'")
        task = task[:18] + "…" if len(task) > 18 else task
        lines.append(f"{m['date'][5:]} {bar} {m['rating']} {task}")

    # Insights
    insights = [f"Average feeling: **{avg(moods):.1f}/5** over {len(moods)} block(s)."]

    if len(moods) >= 6:
        diff = avg(moods[-3:]) - avg(moods[-6:-3])
        if diff >= 0.5:
            insights.append("📈 You're trending **up** lately. Keep doing whatever you're doing.")
        elif diff <= -0.5:
            insights.append("📉 You're trending **down** lately. Maybe it's time for a longer break?")

    bucket_avgs = []
    for name, hours in TIME_BUCKETS:
        group = [m for m in moods if m["hour"] in hours]
        if len(group) >= 2:
            bucket_avgs.append((avg(group), name))
    if len(bucket_avgs) >= 2:
        best_avg, best_name = max(bucket_avgs)
        insights.append(f"⏰ You feel most focused in the **{best_name}** ({best_avg:.1f} avg).")

    clean = [m for m in moods if m["slacks"] == 0]
    slacky = [m for m in moods if m["slacks"] > 0]
    if clean and slacky:
        insights.append(
            f"🔎 Clean blocks feel like **{avg(clean):.1f}/5**. Blocks where I caught you slacking feel like **{avg(slacky):.1f}/5**."
        )

    mismatch = sum(1 for m in moods if m["rating"] >= 4 and m["slacks"] >= 2)
    if mismatch:
        insights.append(f"🤨 You felt great but got caught slacking 2+ times in **{mismatch}** block(s).")

    embed = discord.Embed(title=f"{ctx.author.display_name}'s mood chart", color=discord.Color.pink())
    embed.add_field(name="Trend (oldest → newest)", value=f"`{spark}`", inline=False)
    embed.add_field(name="Recent blocks", value="```\n" + "\n".join(lines) + "\n```", inline=False)
    embed.add_field(name="Insights", value="\n".join(insights), inline=False)
    await ctx.send(embed=embed)

# Custom roasts

@bot.command(name="addroast")
async def addroast(ctx, category: str, *, text: str):
    """!addroast <checkin|on_yes|on_no|on_ignored> <text>. Appends a message."""
    category = category.lower()
    if category not in MESSAGES:
        await ctx.send(f"Category must be one of: {', '.join(MESSAGES.keys())}")
        return

    MESSAGES[category].append(text)
    with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(MESSAGES, f, indent=2, ensure_ascii=False)
    await ctx.send(f"Added to '{category}'. (Edit messages.json to reorder levels)")


@bot.command(name="reloadmsgs")
async def reloadmsgs(ctx):
    try:
        load_messages()
        await ctx.send("Reloaded messages.json")
    except (OSError, json.JSONDecodeError) as e:
        await ctx.send(f"Couldn't reload messages.json: '{e}'")


@bot.command(name="nagshelp")
async def nagshelp(ctx):
    await ctx.send(
        "**🍅 Pomodoro nag bot**\n"
        "'!pomodoro [work] [break] [task]' start a timer (e.g. '!pomodoro 25 5 essay')\n"
        "'!stop' / '!status' / '!resetnag'\n"
        "'!nagmode gentle|normal|drill' how aggressive I am\n"
        "'!dmmode on|off' nag you in Dms instead of the channel\n"
        "'!mystats' / '!leaderboard'\n"
        "'!addroast <category> <text>' / '!reloadmsgs'\n"
        "'!extend [min]' / '!skipbreak' / '!goal [n]'\n"
        "'!pause' / '!resume' / '!hardcore on|off' / '!buddy @user' / '!shamewall on|off'\n"
        "'!weekly' / '!badges' / '!history' / '!hype' / '!roastme'\n"
        "'!preset sprint|classic|long|deep [task]' / '!todo' / '!todo add|done'\n"
        "'!chatwatch on|off' / '!team' / '!teamgoal <hours>'\n"
    )


if __name__ == "__main__":
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set in the .env file or environment.")
    bot.run(token, log_handler=handler, log_level=logging.DEBUG)
