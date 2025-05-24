import discord
from discord.ext import commands
import os
import random
from tinydb import TinyDB, Query


#initalize the bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# initialize the database
db = TinyDB('comfyword_data.json')
game_state_table = db.table('game_state_table')
guesses_table = db.table('guesses')
scoreboard_table = db.table('scoreboard')

# import the words file
def load_words(filename="words.txt"):
    with open(filename, "r") as file:
        return [line.strip() for line in file if line.strip()]

# starts the game
@bot.tree.command(name="start_game",
                  description="Starts a new round of the game (Admin only)")
async def start_game(interaction: discord.Interaction):
    # check if the user has admin privileges
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "Only admins can start the game", ephemeral=True)
        return

    # defer response to avoid timeout
    await interaction.response.defer(ephemeral=True)

    # creates the list of players, and makes sure that there are enough players to start the game
    players = get_players_with_game_role(interaction.guild)
    if len(players) < 3:
        await interaction.followup.send(
            "You need at least 3 players to start the game.", ephemeral=True)
        return

    # double checks that the words file is loaded
    words = load_words()
    if len(words) < 2:
        await interaction.followup.send(
            "Word list is too short or not loaded.", ephemeral=True)
        return

    # randomly assigns roles among players
    sender = random.choice(players)
    receiver = random.choice([p for p in players if p != sender])

    # selects the secret and identification words uniquely
    secret_word = random.choice(words)
    id_word = random.choice([w for w in words if w != secret_word])

    # stores the game state in the database
    game_state_table.upsert({
        "guild_id": interaction.guild_id,
        "sender_id": sender.id,
        "receiver_id": receiver.id,
        "secret_word": secret_word,
        "id_word": id_word,
    }, Query().guild_id == interaction.guild_id)

    # clears the guesses from any previous rounds
    guesses_table.remove(Query().guild_id == interaction.guild_id)

    # DM the sender
    try:
        await sender.send(
            f"You are the **Sender**.\n"
            f"Your secret word is: **{secret_word}**\n"
            f"Your identification word (to help find the receiver) is: **{id_word}**"
        )
    except:
        await interaction.followup.send(f"Couldn't DM {sender.display_name}.",
                                        ephemeral=True)
        return

    # DM the receiver
    try:
        await receiver.send(
            f"You are the **Receiver**.\n"
            f"The Sender is: **{sender.display_name}**\n"
            f"Your identification word (to help find the sender) is: **{id_word}**"
        )
    except:
        await interaction.followup.send(
            f"Couldn't DM {receiver.display_name}.", ephemeral=True)
        return

    await interaction.followup.send(
        "Game started! Roles and words have been sent via DM.", ephemeral=False)


# allows the player to make a guess on the sender, receiver, and secret word
@bot.tree.command(name="guess", description="Submit your guess privately")
async def guess(interaction: discord.Interaction, sender: discord.Member,
                receiver: discord.Member, secret_word: str):
    guild_id = interaction.guild_id
    user_id = interaction.user.id

    game = game_state_table.search(Query().guild_id == guild_id)
    game = game[0]

    sender_id = game.get("sender_id")
    receiver_id = game.get("receiver_id")

    guesses = guesses_table.search(Query().guild_id == guild_id)

    # overwrite existing guess if user already guessed
    guesses = [g for g in guesses if g["user_id"] != user_id]

    # stores the game state in the database
    guesses_table.upsert({
        "guild_id": interaction.guild_id,
        "user_id": user_id,
        "user_name": interaction.user.display_name,
        "guess_sender_id": sender.id,
        "guess_sender_name": sender.display_name,
        "guess_receiver_id": receiver.id,
        "guess_receiver_name": receiver.display_name,
        "guess_secret_word": secret_word.strip()
    }, (Query().guild_id == guild_id) & (Query().user_id == user_id))

    await interaction.response.send_message(
        "Your guess has been recorded.\n\n"
        f"**You guessed:**\n"
        f"- Sender: **{sender.display_name}**\n"
        f"- Receiver: **{receiver.display_name}**\n"
        f"- Secret Word: **{secret_word}**",
        ephemeral=True)


# allows an administrator to view the guesses table
@bot.tree.command(
    name="view_guesses",
    description="View all recorded guesses for this round (Admin only)")
async def view_guesses(interaction: discord.Interaction):
    # check if user is admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "Only admins can view guesses.", ephemeral=True)
        return

    guild_id = interaction.guild_id
    guesses = guesses_table.search(Query().guild_id == guild_id)

    if not guesses:
        await interaction.response.send_message(
            "No guesses have been recorded.", ephemeral=True)
        return

    message = "**Submitted Guesses:**\n\n"
    for guess in guesses:
        message += (f"- **{guess['user_name']}** guessed:\n"
                    f"  - Sender: **{guess['guess_sender_name']}**\n"
                    f"  - Receiver: **{guess['guess_receiver_name']}**\n"
                    f"  - Secret Word: **{guess['guess_secret_word']}**\n\n")

    await interaction.response.send_message(message, ephemeral=True)


# allows a user to view their current guess
@bot.tree.command(
    name="view_my_guess",
    description="View your recorded guess for this round")
async def view_my_guess(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    user_id = interaction.user.id
    guesses = guesses_table.search((Query().guild_id == guild_id) & (Query().user_id == user_id))

    if not guesses:
        await interaction.response.send_message(
            "No guess has been recorded.", ephemeral=True)
        return

    message = "**Submitted Guess:**\n\n"
    for guess in guesses:
        message += (f"- **{guess['user_name']}** guessed:\n"
                    f"  - Sender: **{guess['guess_sender_name']}**\n"
                    f"  - Receiver: **{guess['guess_receiver_name']}**\n"
                    f"  - Secret Word: **{guess['guess_secret_word']}**\n\n")

    await interaction.response.send_message(message, ephemeral=True)


# Set a user's points (Admin only)
@bot.tree.command(name="set_points",
                  description="Set a user's points (Admin only)")
async def set_points(interaction: discord.Interaction, user: discord.Member,
                     points: int):
    guild_id = interaction.guild_id
    user_id = user.id

    # check if user is admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Only admins can set points.",
                                                ephemeral=True)
        return

    # set the user's points
    scoreboard_table.upsert({
        "guild_id": guild_id,
        "user_id": user_id,
        "points": points
    }, (Query().guild_id == guild_id) & (Query().user_id == user_id))

    # send the user's points in an ephemeral message
    await interaction.response.send_message(
        f"Updated {user.mention} to {points} points.", ephemeral=True)


# Check the amount of points a user has
@bot.tree.command(name="get_points", description="Check a user's points")
async def get_points(
    interaction: discord.Interaction,
    user: discord.Member,
):
    guild_id = interaction.guild_id
    user_id = user.id

    # get the join of the guild db and the user db
    result = scoreboard_table.get((Query().guild_id == guild_id) & (Query().user_id == user_id))

    # get the user's points, otherwise default to 0
    points = result["points"] if result else 0

    # send the user's points in an ephemeral message
    await interaction.response.send_message(
        f"{user.mention} has **{points}** points.", ephemeral=True)


@bot.tree.command(name="view_scoreboard",
                  description="View the current game leaderboard")
async def view_scoreboard(interaction: discord.Interaction):
    leaderboard = await build_scoreboard_text(interaction, interaction.guild_id)

    # empty return because build_scoreboard_text already handles the error response
    if leaderboard is None:
        return

    # returns scoreboard
    await interaction.response.send_message(
        f"**Leaderboard:**\n{leaderboard}", ephemeral=True)


# game end helper function for building scoreboard
async def build_scoreboard_text(interaction, guild_id):
    # gets all scoreboard entries for this guild
    entries = scoreboard_table.search(Query().guild_id == guild_id)

    # catch empty scores table
    if not entries:
        await interaction.response.send_message(
            "No scores have been recorded yet.", ephemeral=True)
        return

    # sort entries by points, descending
    sorted_entries = sorted(entries, key=lambda x: x.get("points", 0), reverse=True)

    lines = []
    for entry in sorted_entries:
        user = interaction.guild.get_member(int(entry["user_id"]))
        name = user.display_name if user else f"User {entry['user_id']}"
        points = entry.get("points", 0)
        lines.append(f"**{name}** — {points} point{'s' if points != 1 else ''}")

    leaderboard = "\n".join(lines)
    return (leaderboard)


# adds points to the database for the end game function
def add_points(guild_id, user_id, points):
    # checks to see if the user exists with a score
    existing = scoreboard_table.get(
        (Query().guild_id == guild_id) & (Query().user_id == user_id)
    ) or {}
    
    # sets the new points value, defaulting to 0 if there are no points
    new_points = existing.get("points", 0) + points

    # write the new points to the user given in the function parameters
    scoreboard_table.upsert({
        "guild_id": guild_id,
        "user_id": user_id,
        "points": new_points
    }, (Query().guild_id == guild_id) & (Query().user_id == user_id))


# ends the game
@bot.tree.command(
    name="end_game",
    description="End the current game and reveal results. (Admin only)")
async def end_game(interaction: discord.Interaction):
    # check if user is admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "Only admins can end the game.", ephemeral=True)
        return

    guild_id = interaction.guild_id



    # import the game data and guesses
    game_data = game_state_table.get(Query().guild_id == guild_id)
    guesses = guesses_table.search(Query().guild_id == guild_id)

    # define the senders and receivers
    sender_id = game_data["sender_id"]
    receiver_id = game_data["receiver_id"]
    secret_word = game_data["secret_word"]
    id_word = game_data["id_word"]

    sender = interaction.guild.get_member(int(sender_id))
    receiver = interaction.guild.get_member(int(receiver_id))



    # assign points based on guesses
    receiver_guessed_correctly = False
    players_guessed_secret = False
    # array to track user_id, points for use in building round end scoreboard
    point_changes = []

    for guess in guesses:
        # get the guesser, the guessed sender, guessed receiver, and guessed secret word
        user_id = guess["user_id"]
        guessed_sender = guess["guess_sender_id"]
        guessed_receiver = guess["guess_receiver_id"]
        guessed_word = guess["guess_secret_word"]
        points = 0

        # determine if the receiver guessed the secret word correctly, and assign players points based on their guesses
        # receiver
        if user_id == receiver_id:
            if guessed_word.lower() == secret_word.lower():
                receiver_guessed_correctly = True

        # sender (currently not getting dedicated points for balance reasons)
        #elif user_id == sender_id:
        #guessed_receiver == receiver_id:
        #    points += 1

        # player
        elif user_id != sender_id:
            if guessed_sender == sender_id:
                points += 1
            if guessed_receiver == receiver_id:
                points += 1
            if guessed_word.lower() == secret_word.lower():
                points += 3
                players_guessed_secret = True
            add_points(guild_id, user_id, points)
            point_changes.append({"user_id": user_id, "points": points})



    # assign sender & receiver bonus points
    if receiver_guessed_correctly and not players_guessed_secret:
        add_points(guild_id, sender_id, 5)
        point_changes.append({"user_id": sender_id, "points": 5})
        add_points(guild_id, receiver_id, 5)
        point_changes.append({"user_id": receiver_id, "points": 5})
    else:
        point_changes.append({"user_id": sender_id, "points": 0})
        point_changes.append({"user_id": receiver_id, "points": 0})

    scoreboard_text = await build_scoreboard_text(interaction, guild_id)

    # build the results message
    results = [
        f"**The round has ended! Here are the results:**",
        f" - **Sender:** {sender.mention if sender else f'<@{sender_id}>'}",
        f" - **Receiver:** {receiver.mention if receiver else f'<@{receiver_id}>'}",
        f" - **Secret Word: {secret_word}**",
        f" - **Identification Word: {id_word}**", "\n\n**Player Guesses:**"
    ]

    if not guesses:
        results.append("No guesses were submitted.")
    else:
        for g in guesses:
            point_change_dict = next((item for item in point_changes if item["user_id"] == g['user_id']), None)

            results.append(f"• **{g['user_name']}** guessed: "
                           f"\tSender: {g['guess_sender_name']}"
                           f"\tReceiver: {g['guess_receiver_name']}"
                           f"\tSecret Word: {g['guess_secret_word']}"
                           f"\tPoints Earned: {point_change_dict.get('points')}"
                          )

    await interaction.response.send_message("\n".join(results))
    await interaction.followup.send(f"**Current Scores:**\n{scoreboard_text}")


# command to poll the players for the view_players command
def get_players_with_game_role(guild):
    game_role = discord.utils.get(guild.roles, name="comfyword player")
    return game_role.members if game_role else []


# lists all players with the game role
@bot.tree.command(
    name="view_players",
    description="Lists all members with the 'comfyword player' role")
async def view_players(interaction: discord.Interaction):
    players = get_players_with_game_role(interaction.guild)
    if not players:
        await interaction.response.send_message(
            "No players have the 'comfyword player' role yet!", ephemeral=True)
        return

    player_list = "\n".join([f"- {player.display_name}" for player in players])
    await interaction.response.send_message(
        f"**Players with the 'comfyword player' role:**\n{player_list}",
        ephemeral=True)


# slash command setup / syncing
@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s).")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

    print(f'Connected to {len(bot.guilds)} servers:')
    for guild in bot.guilds:
        print(f'- {guild.name} (ID: {guild.id})')

bot.run(os.environ['WORD_DISCORD_TOKEN'])
