import os
import disnake
from disnake.ext import commands
from dotenv import load_dotenv
from datetime import datetime
import pytz

load_dotenv()

TOKEN = os.getenv('DISCORD_BOT_TOKEN')

intents = disnake.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Support multiple channels
orders = {}  # {channel_id: current_order}
order_messages = {}  # {channel_id: order_message}
last_order_backups = {}  # {channel_id: last_order_backup}
final_order_messages = {}  # {channel_id: final_order_message}

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    print("Bot is ready.")
    for channel in bot.get_all_channels():
        if channel.name.startswith("food-order"):
            print(f"Channel '{channel.name}' found.")
            await clear_and_initialize_channel(channel)

def is_allowed_channel(interaction):
    return interaction.channel.name.startswith("food-order")

async def clear_and_initialize_channel(channel):
    channel_id = channel.id
    async for message in channel.history(limit=100):
        await message.delete()
    order_messages[channel_id] = await channel.send("No active order.")

@bot.event
async def on_message(message):
    channel_id = message.channel.id
    if (isinstance(message.channel, disnake.TextChannel)
        and message.channel.name.startswith("food-order")
        and channel_id in orders):
        if message.author == bot.user:
            return
        await message.delete()

@bot.slash_command(name="startorder", description="Start a new food order")
async def start_order(interaction: disnake.ApplicationCommandInteraction, place: str, time: str):
    if not is_allowed_channel(interaction):
        await interaction.response.send_message("This command can only be used in a food-order channel.", ephemeral=True)
        return

    channel_id = interaction.channel.id

    if channel_id in orders:
        await interaction.user.send("An order is already in progress.")
        await interaction.response.send_message("An order is already in progress.", ephemeral=True)
        return

    async for message in interaction.channel.history(limit=100):
        if channel_id in order_messages and message.id != order_messages[channel_id].id:
            await message.delete()

    cet_tz = pytz.timezone("Europe/Copenhagen")
    start_time = datetime.now(pytz.utc).astimezone(cet_tz).strftime("%Y-%m-%d %H:%M:%S")

    orders[channel_id] = {
        'starter': interaction.user.id,
        'username': interaction.user.name,
        'place': place,
        'time': time,
        'start_time': start_time,
        'items': {}
    }

    await update_order_message(interaction, force_new=True)
    await interaction.response.send_message("Order started!", ephemeral=True)

async def update_order_message(interaction, force_new=False):
    channel_id = interaction.channel.id

    if force_new and channel_id in order_messages:
        try:
            await order_messages[channel_id].delete()
        except disnake.NotFound:
            pass
        order_messages[channel_id] = None

    order = orders.get(channel_id)
    if not order:
        content = "No active order."
    else:
        order_list = [
            f'{interaction.guild.get_member(uid).mention}: {", ".join(items)}'
            for uid, items in order['items'].items()
        ]
        content = (f'Order in progress by {order["username"]}\n\n'
                   f'From: {order["place"]} \nOrder before: {order["time"]}\n'
                   f'Started at: {order["start_time"]}\n\n'
                   'Use "/addorder [order]" to order your food.\n' +
                   ('Current orders:\n' + '\n'.join(order_list) if order_list else "No orders yet."))

    if channel_id not in order_messages or order_messages[channel_id] is None:
        order_messages[channel_id] = await interaction.channel.send(content)
    else:
        await order_messages[channel_id].edit(content=content)

@bot.slash_command(name="addorder", description="Add an item to the current order (overwrites previous)")
async def add_order(interaction: disnake.ApplicationCommandInteraction, order: str):
    if not is_allowed_channel(interaction):
        await interaction.response.send_message("This command can only be used in a food-order channel.", ephemeral=True)
        return

    channel_id = interaction.channel.id
    current_order = orders.get(channel_id)
    if not current_order:
        await interaction.user.send("No active order. Start an order using /startorder.")
        await interaction.response.send_message("No active order.", ephemeral=True)
        return

    current_order['items'][interaction.user.id] = [order]
    await update_order_message(interaction)
    await interaction.response.send_message("Your order has been updated!", ephemeral=True)

@bot.slash_command(name="endorder", description="Finalize the current order")
async def finalize_order(interaction: disnake.ApplicationCommandInteraction, mobilepay: str = None):
    if not is_allowed_channel(interaction):
        await interaction.response.send_message("This command can only be used in a food-order channel.", ephemeral=True)
        return

    channel_id = interaction.channel.id
    current_order = orders.get(channel_id)
    if not current_order:
        await interaction.user.send("No active order to finalize.")
        await interaction.response.send_message("No active order to finalize.", ephemeral=True)
        return

    last_order_backups[channel_id] = current_order.copy()

    order_list = []
    for user_id, user_orders in current_order['items'].items():
        member = interaction.guild.get_member(user_id)
        if member:
            order_list.append(f'{member.mention}: {", ".join(user_orders)}')
        else:
            order_list.append(f'Unknown User ({user_id}): {", ".join(user_orders)}')

    order_list_message = "The following order has been ended:\n" + '\n'.join(order_list)
    if mobilepay:
        order_list_message += f"\n\nPlease MobilePay to the following number: {mobilepay}"

    final_order_messages[channel_id] = await interaction.channel.send(order_list_message)
    await interaction.user.send(
    f"Order finalized for **{current_order['place']}**:\n\n"
    f"{order_list_message}\n\n"
    "If you ended it by mistake, you can use `/restoreorder` to restore the last order."
)


    del orders[channel_id]
    await update_order_message(interaction)
    await interaction.response.send_message("Order finalized!", ephemeral=True)

@bot.slash_command(name="restoreorder", description="Restore the last ended order")
async def restore_order(interaction: disnake.ApplicationCommandInteraction):
    if not is_allowed_channel(interaction):
        await interaction.response.send_message("This command can only be used in a food-order channel.", ephemeral=True)
        return

    channel_id = interaction.channel.id
    if channel_id in orders:
        await interaction.response.send_message("An order is already in progress.", ephemeral=True)
        return

    if channel_id not in last_order_backups:
        await interaction.response.send_message("No order available to restore.", ephemeral=True)
        return

    if final_order_messages.get(channel_id):
        await final_order_messages[channel_id].delete()
        final_order_messages[channel_id] = None

    orders[channel_id] = last_order_backups[channel_id]
    await update_order_message(interaction)
    await interaction.response.send_message("The previous order has been restored.", ephemeral=True)

@bot.slash_command(name="clearorder", description="Remove your order from the current order")
async def clear_order(interaction: disnake.ApplicationCommandInteraction):
    if not is_allowed_channel(interaction):
        await interaction.response.send_message("This command can only be used in a food-order channel.", ephemeral=True)
        return

    channel_id = interaction.channel.id
    current_order = orders.get(channel_id)
    if not current_order:
        await interaction.user.send("No active order to modify.")
        await interaction.response.send_message("No active order to modify.", ephemeral=True)
        return

    if interaction.user.id not in current_order['items']:
        await interaction.user.send("You have no items in the current order.")
        await interaction.response.send_message("You have no items in the current order.", ephemeral=True)
        return

    del current_order['items'][interaction.user.id]
    await update_order_message(interaction)
    await interaction.response.send_message("Your order has been removed!", ephemeral=True)

@bot.slash_command(name="help", description="Shows a list of available commands")
async def help_command(interaction: disnake.ApplicationCommandInteraction):
    help_text = (
        "Hello\n"
        "My name is FoodBot, I help you organize a food order.\n\n"
        "/startorder [place] [time] - Starts a new food order\n"
        "/addorder [order] - Add an item to the current order\n"
        "/endorder - Finalize the current order\n"
        "/clearorder - Remove your order from the current order\n"
        "/restoreorder - Restore the last ended order if ended by mistake\n"
        "/help - Show this help message"
    )
    await interaction.response.send_message("A list of commands has been sent to your DMs!", ephemeral=True)
    await interaction.user.send(help_text)

bot.run(TOKEN)
