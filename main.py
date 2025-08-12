
import os
import discord
from discord import app_commands, Interaction, Embed, ButtonStyle
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = 1404884398079213698  # Replace with your server's ID

# Validate token
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN environment variable is not set! Please add it to your Secrets.")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="rk!", intents=intents)
tree = bot.tree

# Global submission channel ID
SUBMISSION_CHANNEL_ID = 1404896507626520729

# MongoDB setup
MONGO_URI = "mongodb+srv://rkdon:R4JK4ND3L@rkdon.nmj3mpp.mongodb.net/?retryWrites=true&w=majority&appName=rkdon"
mongo_enabled = False
verify_setup = {}
mongo_client = None
mongo_db = None
mongo_coll = None

# Initialize MongoDB connection
if MONGO_URI:
    try:
        import motor.motor_asyncio
        # Add more robust connection options
        mongo_client = motor.motor_asyncio.AsyncIOMotorClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,  # 5 second timeout
            connectTimeoutMS=5000,
            socketTimeoutMS=5000,
            tls=True,
            tlsAllowInvalidCertificates=True,  # For compatibility with some hosting environments
            retryWrites=True,
            w='majority'
        )
        mongo_db = mongo_client["discord_bot"]
        mongo_coll = mongo_db["verify_setup"]
        mongo_enabled = True
        print("MongoDB connection configured")
    except ImportError:
        print("motor package not installed. Using in-memory storage.")
        mongo_enabled = False
    except Exception as e:
        print(f"MongoDB setup failed: {e}")
        mongo_enabled = False
else:
    print("MONGO_URI not set. Using in-memory storage.")

async def test_mongo_connection():
    """Test MongoDB connection and disable if it fails"""
    global mongo_enabled
    if mongo_enabled and mongo_client:
        try:
            # Test the connection
            await mongo_client.admin.command('ping')
            print("MongoDB connection test successful")
            return True
        except Exception as e:
            print(f"MongoDB connection test failed: {e}")
            mongo_enabled = False
            return False
    return False

async def get_verify_setup(guild_id):
    """Get verification setup for a guild"""
    if mongo_enabled:
        try:
            doc = await mongo_coll.find_one({"guild_id": guild_id})
            if doc:
                return {"channel_id": doc["channel_id"], "role_id": doc["role_id"]}
            else:
                return None
        except Exception as e:
            print(f"MongoDB read error: {e}")
            return verify_setup.get(guild_id)
    else:
        return verify_setup.get(guild_id)

async def set_verify_setup(guild_id, channel_id, role_id):
    """Set verification setup for a guild"""
    global mongo_enabled
    if mongo_enabled:
        try:
            await mongo_coll.update_one(
                {"guild_id": guild_id},
                {"$set": {"channel_id": channel_id, "role_id": role_id}},
                upsert=True
            )
        except Exception as e:
            print(f"MongoDB write error: {e}. Falling back to in-memory storage.")
            mongo_enabled = False
            verify_setup[guild_id] = {
                "channel_id": channel_id,
                "role_id": role_id
            }
    else:
        verify_setup[guild_id] = {
            "channel_id": channel_id,
            "role_id": role_id
        }

@tree.command(name="setverify", description="Setup the verification panel channel and role.")
@app_commands.describe(
    channel="The channel where the verification panel will be sent",
    role="The role that will be given to verified users"
)
async def setverify(interaction: Interaction, channel: discord.TextChannel, role: discord.Role):
    """Set up verification system for the server"""
    await set_verify_setup(interaction.guild.id, channel.id, role.id)
    await interaction.response.send_message(
        content=f"<a:approved:1404893665884635268> Setup complete!\n**Channel:** {channel.mention}\n**Role:** {role.mention}\n\nUse `/sendverifypanel` to send the panel.",
        ephemeral=True
    )

@tree.command(name="sendverifypanel", description="Send the verification panel in the configured channel.")
async def sendverifypanel(interaction: Interaction):
    """Send the verification panel to the configured channel"""
    setup = await get_verify_setup(interaction.guild.id)
    if not setup:
        await interaction.response.send_message("Verification setup not found. Use `/setverify` first.", ephemeral=True)
        return
    
    channel = interaction.guild.get_channel(setup["channel_id"])
    role = interaction.guild.get_role(setup["role_id"])
    
    if not channel or not role:
        await interaction.response.send_message("Invalid channel or role. Check IDs.", ephemeral=True)
        return
    
    embed = Embed(
        title="Verification Panel",
        description=f"**\n- Click on Verify button below to get verified \n- Verification Role: {role.mention}\n**",
        color=0x00ffff
    )
    
    view = PersistentVerifyView()
    
    try:
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message("Panel sent!", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("I don't have permission to send messages in that channel!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to send panel: {str(e)}", ephemeral=True)

class PersistentVerifyView(View):
    """Persistent view for verification button that survives bot restarts"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Verify", style=ButtonStyle.blurple, custom_id="persistent_verify_btn")
    async def verify_button(self, interaction: Interaction, button: Button):
        # Get the verification setup for this guild
        setup = await get_verify_setup(interaction.guild.id)
        if not setup:
            await interaction.response.send_message("Verification setup not found. Please contact an administrator.", ephemeral=True)
            return
        
        role = interaction.guild.get_role(setup["role_id"])
        if not role:
            await interaction.response.send_message("Verification role not found. Please contact an administrator.", ephemeral=True)
            return
        
        # Check if user already has the verification role
        if role in interaction.user.roles:
            embed = Embed(
                title="Already Verified",
                description="<a:processing:1404893899167629385> **You are already verified in this server!**",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        channel = interaction.guild.get_channel(setup["channel_id"])
        await interaction.response.send_modal(VerifyFormModal(role=role, panel_channel=channel))

class VerifyFormModal(Modal, title="Verification Form"):
    """Modal form for user verification"""
    
    def __init__(self, role, panel_channel):
        super().__init__()
        self.role = role
        self.panel_channel = panel_channel

        self.full_name = TextInput(
            label="Full Name", 
            placeholder="Enter your full name (e.g. John Doe)", 
            required=True,
            max_length=100
        )
        self.country_code = TextInput(
            label="Country Code", 
            placeholder="Enter your country code (e.g. +977, +91, +1)", 
            required=True,
            max_length=5
        )
        self.number = TextInput(
            label="Phone Number", 
            placeholder="Enter 10 digit phone number (without country code)", 
            required=True,
            max_length=15
        )
        self.email = TextInput(
            label="Email Address", 
            placeholder="Enter your email address (e.g. john@example.com)", 
            required=True,
            max_length=100
        )
        self.additional_info = TextInput(
            label="Additional Information (Optional)", 
            placeholder="Any additional information you'd like to share", 
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=500
        )

        self.add_item(self.full_name)
        self.add_item(self.country_code)
        self.add_item(self.number)
        self.add_item(self.email)
        self.add_item(self.additional_info)

    async def on_submit(self, interaction: Interaction):
        """Handle form submission and validate data"""
        # Validate phone number
        if not self.number.value.isdigit() or len(self.number.value) < 8 or len(self.number.value) > 15:
            embed = Embed(
                title="❌ Verification Failed",
                description="<a:processing:1404893899167629385> **Invalid phone number! Must be 8-15 digits.**",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Validate email format (basic check)
        if "@" not in self.email.value or "." not in self.email.value.split("@")[-1]:
            embed = Embed(
                title="❌ Verification Failed",
                description="<a:processing:1404893899167629385> **Invalid email format! Please enter a valid email address.**",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Validate country code format
        if not self.country_code.value.startswith("+") or not self.country_code.value[1:].isdigit():
            embed = Embed(
                title="❌ Verification Failed",
                description="<a:processing:1404893899167629385> **Invalid country code! Must start with + followed by digits.**",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            # Assign role
            await interaction.user.add_roles(self.role)
            
            # Send details to the global submission channel
            submission_channel = interaction.client.get_channel(SUBMISSION_CHANNEL_ID)
            if submission_channel:
                details_embed = Embed(
                    title="📋 New Verification Submission",
                    description="A user has successfully completed verification.",
                    color=0x00ffff,
                    timestamp=interaction.created_at
                )
                details_embed.set_thumbnail(url=interaction.user.display_avatar.url)
                details_embed.add_field(name="🏠 Server", value=f"{interaction.guild.name}\n`ID: {interaction.guild.id}`", inline=True)
                details_embed.add_field(name="👤 User", value=f"{interaction.user.mention}\n`{interaction.user} (ID: {interaction.user.id})`", inline=True)
                details_embed.add_field(name="🎭 Role Assigned", value=self.role.mention, inline=True)
                details_embed.add_field(name="📛 Full Name", value=f"`{self.full_name.value}`", inline=True)
                details_embed.add_field(name="🌍 Country Code", value=f"`{self.country_code.value}`", inline=True)
                details_embed.add_field(name="📞 Phone Number", value=f"`{self.country_code.value} {self.number.value}`", inline=True)
                details_embed.add_field(name="📧 Email", value=f"`{self.email.value}`", inline=False)
                
                if self.additional_info.value and self.additional_info.value.strip():
                    details_embed.add_field(name="ℹ️ Additional Info", value=f"```{self.additional_info.value[:500]}```", inline=False)
                
                details_embed.set_footer(text="Verification completed at")
                
                try:
                    await submission_channel.send(embed=details_embed)
                except Exception as e:
                    print(f"Failed to send submission to channel: {e}")

            success_embed = Embed(
                title="✅ Verification Complete!",
                description=f"<a:approved:1404893665884635268> **Congratulations!** You have been successfully verified and given the role: {self.role.mention}\n\nWelcome to **{interaction.guild.name}**!",
                color=0x00ff00
            )
            await interaction.response.send_message(embed=success_embed, ephemeral=True)
            
        except discord.Forbidden:
            error_embed = Embed(
                title="❌ Verification Failed",
                description="<a:processing:1404893899167629385> **I don't have permission to assign roles! Please contact an administrator.**",
                color=0xff0000
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
        except Exception as e:
            error_embed = Embed(
                title="❌ Verification Failed",
                description=f"<a:processing:1404893899167629385> **An error occurred: {str(e)}**",
                color=0xff0000
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)

@bot.event
async def on_ready():
    """Event triggered when bot is ready"""
    print(f"Bot logged in as {bot.user}")
    
    # Test MongoDB connection
    if mongo_enabled:
        await test_mongo_connection()
    
    # Add persistent view to handle verification buttons after restart
    bot.add_view(PersistentVerifyView())
    print("Added persistent verify view")
    
    # Set bot status
    await bot.change_presence(activity=discord.Game(name="with gf (.) (.)"))
    
    try:
        # Sync commands globally first
        synced_global = await tree.sync()
        print(f"Synced {len(synced_global)} commands globally")
        
        # Then sync to specific guild for faster updates
        synced_guild = await tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"Synced {len(synced_guild)} commands for guild {GUILD_ID}")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.event
async def on_command_error(ctx, error):
    """Handle command errors"""
    if isinstance(error, commands.CommandNotFound):
        print(f"Command not found: {ctx.message.content}")
    else:
        print(f"Command error: {error}")

@bot.event
async def on_app_command_error(interaction: discord.Interaction, error):
    """Handle application command errors"""
    if isinstance(error, app_commands.CommandNotFound):
        await interaction.response.send_message("Command not found. Please wait for commands to sync.", ephemeral=True)
    else:
        print(f"App command error: {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message("An error occurred while processing the command.", ephemeral=True)

if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("Invalid Discord bot token! Please check your DISCORD_BOT_TOKEN secret.")
    except Exception as e:
        print(f"Failed to start bot: {e}")
