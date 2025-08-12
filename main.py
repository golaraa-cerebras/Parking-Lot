
import os
import time
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
import atexit
load_dotenv()

# Initialize the app with your bot token
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# Configure the number of spots
NUM_SPOTS = 2  # Change this number to set how many spots you want

# Track spot assignments: {spot_number: {'user_id': user_id, 'timestamp': timestamp}}
spot_assignments = {}
# Track spot status: {spot_number: "available"/"taken"}
spot_status = {i: "available" for i in range(1, NUM_SPOTS + 1)}
# Queue for users waiting for spots
waiting_queue = []

def get_next_available_spot():
    """Return the lowest-numbered available spot or None if all are taken"""
    for spot in range(1, NUM_SPOTS + 1):
        if spot_status[spot] == "available":
            return spot
    return None

def assign_next_person_to_spot(spot, say, channel):
    """Assign the next person in queue to an available spot"""
    if waiting_queue:
        next_user = waiting_queue.pop(0)  # Get first person in queue
        spot_assignments[spot] = {'user_id': next_user, 'timestamp': time.time()}
        spot_status[spot] = "taken"
        say(f" Assigned <@{next_user}> to spot #{spot} from waiting queue")
        return True
    return False

def show_spot_assignments(say):
    """Show who has which spot"""
    if not spot_assignments:
        say("No spots are currently assigned.")
        return
    
    lines = ["🚗 Current spot assignments:"]
    for spot in range(1, NUM_SPOTS + 1):
        if spot in spot_assignments:
            user_id = spot_assignments[spot]['user_id']
            lines.append(f"Spot #{spot}: <@{user_id}>")
        else:
            lines.append(f"Spot #{spot}: Available")
    say("\n".join(lines))
    
    if len(waiting_queue) > 0:
        lines = ["🚗 Current queue:"]
        for item in waiting_queue:
            lines.append(f"<@{item}>")
        say("\n".join(lines))
    else:
        say("No one is currently in the queue.")
        
    

# Case-insensitive message handler
@app.message()
def handle_commands(message, say):
    text = message.get('text', '').strip()
    user_id = message['user']
    channel = message['channel']
    
    # Convert to uppercase for case-insensitive comparison
    command = text.upper()
    
    if command == "Q":
        assign_spot(message, say, channel)
    elif command == "SO":
        mark_spot_available(message, say)
    elif command == "CHECK":
        check_long_parking(message, say)
    elif command == "LINE":
        show_spot_assignments(say)
    else:
        # Ignore non-recognized messages
        return

def assign_spot(message, say, channel):
    user_id = message['user']
    
    # Check if user already has a spot
    for spot, data in spot_assignments.items():
        if data['user_id'] == user_id:
            say(f"<@{user_id}> You already have spot #{spot}")
            return
    
    # Get next available spot
    spot = get_next_available_spot()
    if spot:
        spot_assignments[spot] = {'user_id': user_id, 'timestamp': time.time()}
        spot_status[spot] = "taken"
        say(f" Assigned <@{user_id}> to spot #{spot}")
    else:
        # Add user to waiting queue
        if user_id not in waiting_queue:
            waiting_queue.append(user_id)
        say(f"No spots available for <@{user_id}>. Added to waiting queue.")

def mark_spot_available(message, say):
    user_id = message['user']
    channel = message['channel']
    
    # Find and free user's spot
    spot = next((s for s, data in spot_assignments.items() if data['user_id'] == user_id), None)
    if spot:
        del spot_assignments[spot]
        spot_status[spot] = "available"
        
        # Try to assign spot to next person in queue
        if assign_next_person_to_spot(spot, say, channel):
            say(f"Spot #{spot} is now available and assigned to next person in queue")
        else:
            say(f"Spot #{spot} is now available")
    else:
        say(f"<@{user_id}> You don't have an assigned spot yet, please wait!")

# Check for long parking times
def check_long_parking(message, say):
    current_time = time.time()
    three_hours = 3 * 60 * 60  # 1 minute for testing (change to 3*60*60 for 3 hours)
    
    warnings_sent = False
    for spot, data in spot_assignments.items():
        if spot_status[spot] == "taken":
            time_parked = current_time - data['timestamp']
            if time_parked > three_hours:
                user_id = data['user_id']
                hours_parked = time_parked / 3600
                say(f"<@{user_id}> ⚠️ WARNING: You've had spot #{spot} for {hours_parked:.1f} hours. Please move your car!")
                warnings_sent = True
    
    if not warnings_sent:
        say("No cars have been parked for more than 3 hours.")

def send_shutdown_message(channel_name):
    """Send a message when the bot is shutting down"""
    try:
        app.client.chat_postMessage(
            channel=channel_name,
            text="🛑 Parking spot bot is now offline. See you next time!"
        )
    except Exception as e:
        print(f"Could not send shutdown message: {e}")

if __name__ == "__main__":
    print(f"Bot is starting with {NUM_SPOTS} spots...")
    channel_name = "#new-channel"  # Replace with your channel name
    # Register shutdown function
    atexit.register(send_shutdown_message, channel_name)
    
    # Post startup message to a channel by name
    app.client.chat_postMessage(
        channel=channel_name,
        text=f"🚗 Parking spot bot is now online with {NUM_SPOTS} spots! Available commands: `Q` (get spot), `SO` (free spot), `CHECK` (check for warnings), `LINE` (show assignments and queue)"
    )
    
    # Start the app in Socket Mode using your app token
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()