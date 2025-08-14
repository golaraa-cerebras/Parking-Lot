
import os
import time
import re
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
import atexit

load_dotenv()

# Initialize the app with your bot token
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# Configure the number of spots
NUM_SPOTS = 8  # Change this number to set how many spots you want

# Track spot assignments: {spot_number: {'user_id': user_id, 'timestamp': timestamp}}
spot_assignments = {}
# Track spot status: {spot_number: "available"/"taken"/"down"}
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
            status = spot_status[spot]
            if status == "available":
                lines.append(f"Spot #{spot}: Available")
            elif status == "down":
                lines.append(f"Spot #{spot}: ⚠️ DOWN")
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
    # Ignore non-user messages like joins/leaves/etc.
    if 'subtype' in message:
        return

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
    elif command == "P":
        handle_p_command(message, say)
    else:
        # Check for slot down/up commands
        slot_down_match = re.match(r'^SPOT\s+(\d+)\s+DOWN$', command)
        slot_up_match = re.match(r'^SPOT\s+(\d+)\s+UP$', command)
        
        if slot_down_match:
            slot_number = int(slot_down_match.group(1))
            mark_slot_down(slot_number, message, say)
        elif slot_up_match:
            slot_number = int(slot_up_match.group(1))
            mark_slot_up(slot_number, say)
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

    # Get next available spot (excluding down spots)
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
        # Only mark as available if it's not down
        if spot_status[spot] != "down":
            spot_status[spot] = "available"

        # Try to assign spot to next person in queue (only if spot is available, not down)
        if spot_status[spot] == "available":
            if assign_next_person_to_spot(spot, say, channel):
                say(f"Spot #{spot} is now available and assigned to next person in queue")
            else:
                say(f"Spot #{spot} is now available")
        else:
            say(f"Spot #{spot} was freed but remains DOWN")
    else:
        say(f"<@{user_id}> You don't have an assigned spot yet, please wait!")

def handle_p_command(message, say):
    user_id = message['user']
    channel = message['channel']

    # Find the spot that belongs to the user
    spot = next((s for s, data in spot_assignments.items() if data['user_id'] == user_id), None)
    
    if spot:
        # Free up their current spot
        del spot_assignments[spot]
        # Only mark as available if it's not down
        if spot_status[spot] != "down":
            spot_status[spot] = "available"
        say(f"<@{user_id}> passed on spot #{spot}.")

        # Add them to the front of the queue
        if user_id in waiting_queue:
            waiting_queue.remove(user_id)
        waiting_queue.insert(0, user_id)
        say(f"<@{user_id}> moved to the front of the queue.")

        # Assign the freed spot to the next person in queue (only if spot is available, not down)
        if spot_status[spot] == "available":
            assign_next_person_to_spot(spot, say, channel)
    else:
        say(f"<@{user_id}> You don't currently have a spot to pass on.")

def mark_slot_down(slot_number, message, say):
    """Mark a slot as down/maintenance"""
    if slot_number < 1 or slot_number > NUM_SPOTS:
        say(f"Invalid slot number. Please use a number between 1 and {NUM_SPOTS}.")
        return
    
    user_id = message['user']
    
    # Check if user owns this slot
    user_owns_slot = slot_number in spot_assignments and spot_assignments[slot_number]['user_id'] == user_id
    
    # If slot is currently taken, free it and assign to next person
    if spot_status[slot_number] == "taken":
        slot_owner = spot_assignments[slot_number]['user_id']
        del spot_assignments[slot_number]
        # Try to assign to next person in queue
        if assign_next_person_to_spot(slot_number, say, None):
            say(f"Spot #{slot_number} was taken by <@{slot_owner}> but has been freed due to being marked DOWN. Assigned to next person in queue.")
        else:
            say(f"Spot #{slot_number} was taken by <@{slot_owner}> but has been freed due to being marked DOWN.")
    
    spot_status[slot_number] = "down"
    say(f"Spot #{slot_number} has been marked as DOWN ⚠️")
    
    # If the user who marked the slot down was the owner, try to reassign them
    if user_owns_slot:
        # Get next available spot
        next_spot = get_next_available_spot()
        if next_spot:
            spot_assignments[next_spot] = {'user_id': user_id, 'timestamp': time.time()}
            spot_status[next_spot] = "taken"
            say(f"<@{user_id}> has been reassigned to spot #{next_spot}")
        else:
            # Add them to the front of the queue
            if user_id in waiting_queue:
                waiting_queue.remove(user_id)
            waiting_queue.insert(0, user_id)
            say(f"<@{user_id}> added to the front of the queue (no spots available)")

def mark_slot_up(slot_number, say):
    """Mark a slot as available/up"""
    if slot_number < 1 or slot_number > NUM_SPOTS:
        say(f"Invalid slot number. Please use a number between 1 and {NUM_SPOTS}.")
        return
    
    if spot_status[slot_number] == "down":
        spot_status[slot_number] = "available"
        say(f"Spot #{slot_number} has been marked as UP and is now available ✅")
        
        # Try to assign this newly available spot to the next person in queue
        assign_next_person_to_spot(slot_number, say, None)
    else:
        say(f"Spot #{slot_number} is already available or taken.")

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
    channel_name = "#ev-test"  # Replace with your channel name
    # Register shutdown function
    atexit.register(send_shutdown_message, channel_name)

    # Post startup message to a channel by name
    app.client.chat_postMessage(
        channel=channel_name,
        text=f"🚗 Parking spot bot is now online with {NUM_SPOTS} spots! Available commands: `Q` (get spot), `SO` (free spot), `CHECK` (check for warnings), `LINE` (show assignments and queue), `P` (pass spot - give up spot and go to front of queue), `slot <number> down` (mark slot as down), `slot <number> up` (mark slot as available)"
    )

    # Start the app in Socket Mode using your app token
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()