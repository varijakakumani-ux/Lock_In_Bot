import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

secret_role = "working"

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
        await message.delete()
        await message.channel.send(f"{message.author.mention}, please refrain from using inappropriate language.")

    await bot.process_commands(message)

#!hello
@bot.command()
async def hello(ctx):
    await ctx.send(f"Hello, {ctx.author.mention}!")

@bot.command()
async def assign(ctx):
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

bot.run(token, log_handler=handler, log_level=logging.DEBUG)