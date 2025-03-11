import os
import disnake
from disnake.ext import commands
from dotenv import load_dotenv
from datetime import datetime
import pytz

load_dotenv()

TOKEN = os.getenv('DISCORD_BOT_TOKEN')

intents = disnake.Intents.default()
intents.message_content = True  # Enable message content intent
intents.members = True  # Enable members intent

bot = commands.Bot(command_prefix='!', intents=intents)
current_order = None
allowed_channel_name = "food-order"
allowed_channel_name = "food-order"
order_message = None
last_order_backup = None  # Backup variable for the last order

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    print("Bot is ready.")
    channel = disnake.utils.get(bot.get_all_channels(), name=allowed_channel_name)
    if channel:
        print(f"Channel '{allowed_channel_name}' found.")
        await clear_and_initialize_channel(channel)
    else:
        print(f"Channel '{allowed_channel_name}' not found.")

def is_allowed_channel(interaction):
    return interaction.channel.name == allowed_channel_name

async def clear_and_initialize_channel(channel):
    global order_message
    async for message in channel.history(limit=100):
        await message.delete()
    order_message = await channel.send("No active order.")

@bot.event
async def on_message(message):
    if isinstance(message.channel, disnake.TextChannel) and message.channel.name == allowed_channel_name and current_order is not None:
        if message.author == bot.user:
            return
        await message.delete()

@bot.slash_command(name="startorder", description="Start a new food order")
async def start_order(interaction: disnake.ApplicationCommandInteraction, place: str, time: str):
    if not is_allowed_channel(interaction):
        await interaction.response.send_message(f'This command can only be used in the #{allowed_channel_name} channel.', ephemeral=True)
        return

    global current_order
    global order_message  

    if current_order is not None:
        await interaction.user.send('An order is already in progress.')
        await interaction.response.send_message('An order is already in progress.', ephemeral=True)
        return

    channel = interaction.channel
    async for message in channel.history(limit=100):
        if message != order_message:
            await message.delete()

    cet_tz = pytz.timezone("Europe/Copenhagen")
    start_time = datetime.now(pytz.utc).astimezone(cet_tz).strftime("%Y-%m-%d %H:%M:%S")  # Get current time

    current_order = {
        'starter': interaction.user.id, 
        'username': interaction.user.name, 
        'place': place, 
        'time': time, 
        'start_time': start_time,  # Store start time
        'items': {}
    }

    await update_order_message(interaction)
    await interaction.response.send_message('Order started!', ephemeral=True)

async def update_order_message(interaction):
    global order_message
    channel = interaction.channel
    if current_order is None:
        content = "No active order."
    else:
        order_list = [f'{interaction.guild.get_member(user_id).mention}: {", ".join(user_orders)}' for user_id, user_orders in current_order['items'].items()]
        content = (f'Order in progress by {current_order["username"]}\n \n'
                   f'From: {current_order["place"]} \nOrder before: {current_order["time"]}\n'
                   f'Started at: {current_order["start_time"]} \n \n'  # Add start time to the message
                   'Use "/addorder [order]" to order your food.\n' f'Current orders: \n' + '\n'.join(order_list))
    
    if order_message is None:
        order_message = await channel.send(content)
    else:
        await order_message.edit(content=content)

@bot.slash_command(name="addorder", description="Add an item to the current order (will overwrite any previous order)")
async def add_order(interaction: disnake.ApplicationCommandInteraction, order: str):
    if not is_allowed_channel(interaction):
        await interaction.response.send_message(f'This command can only be used in the #{allowed_channel_name} channel.', ephemeral=True)
        return

    global current_order
    if current_order is None:
        await interaction.user.send('No active order. Start an order using /startorder.')
        await interaction.response.send_message('No active order. Start an order using /startorder.', ephemeral=True)
        return

    current_order['items'][interaction.user.id] = [order]
    
    await update_order_message(interaction)
    await interaction.response.send_message('Your order has been updated!', ephemeral=True)

final_order_message = None  # Variable to store the finalized order message

@bot.slash_command(name="endorder", description="Finalize the current order")
async def finalize_order(interaction: disnake.ApplicationCommandInteraction):
    if not is_allowed_channel(interaction):
        await interaction.response.send_message(f'This command can only be used in the #{allowed_channel_name} channel.', ephemeral=True)
        return
    
    global current_order, last_order_backup, final_order_message
    if current_order is None:
        await interaction.user.send('No active order to finalize.')
        await interaction.response.send_message('No active order to finalize.', ephemeral=True)
        return
    
    # Backup the current order before finalizing
    last_order_backup = current_order.copy()

    # Prepare the final order list message with mentions
    order_list = []
    for user_id, user_orders in current_order['items'].items():
        member = interaction.guild.get_member(user_id)
        if member:
            order_list.append(f'{member.mention}: {", ".join(user_orders)}')
        else:
            order_list.append(f'Unknown User ({user_id}): {", ".join(user_orders)}')
    
    # Send the final order list to the channel and save the message reference
    order_list_message = "The following order has been ended:\n" + '\n'.join(order_list)
    final_order_message = await interaction.channel.send(order_list_message)
    
    # Send the finalized order as a DM to the user ending the order
    await interaction.user.send("Order finalized:\n" + '\n'.join(order_list))

    # Clear the current order
    current_order = None
    await update_order_message(interaction)
    await interaction.response.send_message('Order finalized!', ephemeral=True)


@bot.slash_command(name="restoreorder", description="Restore the last ended order if it was ended by mistake")
async def restore_order(interaction: disnake.ApplicationCommandInteraction):
    if not is_allowed_channel(interaction):
        await interaction.response.send_message(f'This command can only be used in the #{allowed_channel_name} channel.', ephemeral=True)
        return
    
    global current_order, last_order_backup, final_order_message
    if current_order is not None:
        await interaction.response.send_message("An order is already in progress, cannot restore another order.", ephemeral=True)
        return
    
    if last_order_backup is None:
        await interaction.response.send_message("No order available to restore.", ephemeral=True)
        return

    # Remove the finalized order message if it exists
    if final_order_message:
        await final_order_message.delete()
        final_order_message = None  # Reset the reference

    # Restore the last backup
    current_order = last_order_backup
    await update_order_message(interaction)
    await interaction.response.send_message("The previous order has been restored.", ephemeral=True)

@bot.slash_command(name="clearorder", description="Remove your order from the current order")
async def clear_order(interaction: disnake.ApplicationCommandInteraction):
    print("clear_order command defined")
    if not is_allowed_channel(interaction):
        await interaction.response.send_message(f'This command can only be used in the #{allowed_channel_name} channel.', ephemeral=True)
        return
    
    global current_order
    if current_order is None:
        await interaction.user.send('No active order to modify.')
        await interaction.response.send_message('No active order to modify.', ephemeral=True)
        return
    
    if interaction.user.id not in current_order['items']:
        await interaction.user.send('You have no items in the current order.')
        await interaction.response.send_message('You have no items in the current order.', ephemeral=True)
        return
    
    del current_order['items'][interaction.user.id]
    await update_order_message(interaction)
    
    await interaction.response.send_message('Your order has been removed!', ephemeral=True)
    print("clear_order command processed")

@bot.slash_command(name="help", description="Shows a list of available commands")
async def help_command(interaction: disnake.ApplicationCommandInteraction):
    print("help command defined")
    help_text = (
        "Hello\n"
        "My name is FoodBot, i help you organize a food order, to use me see my commands below:\n \n"
        "/startorder [place] [time] - Starts a new food order\n \n"
        "/addorder [order] - Add an item to the current order\n \n"
        "/endorder - Finalize the current order\n \n"
        "/clearorder - Remove your order from the current order\n \n"
        "/Restoreorder - Restores the last ended order, if it was ended by mistake\n \n"
        "/help - Show this help message\n \n"
    )
    # Use ephemeral response for the help message to avoid confusion
    await interaction.response.send_message('A list of commands has been sent to your DMs!', ephemeral=True)
    await interaction.user.send(help_text)  # Send the help text to the user's DM
    print("help command processed")


bot.run(TOKEN)
