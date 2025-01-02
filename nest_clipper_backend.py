import os
import datetime
import signal
import threading
import time
import pytz
from glocaltokens.client import GLocalAuthenticationTokens
from app_prefs_database import DatabaseHandler, check_database_exists, get_db_path
from tools import logger
from auth_wrapper import Connection

HOURS_TO_CHECK = 12

class NestClipperBackend:
    def __init__(self):
        self.running = False
        self.refresh_interval = 3600
        self.timer_thread = None
        self.db_handler = DatabaseHandler(get_db_path())

    def authenticate_user(self, email, app_password):
        if not email or not app_password:
            raise ValueError("Email and App Password are required.")

        client = GLocalAuthenticationTokens(username=email, password=app_password)
        master_token = client.get_master_token()

        if not master_token:
            raise ValueError("Invalid Credentials.")

        preferences = {
            "USERNAME": email,
            "MASTER_TOKEN": master_token,
            "MASTER_TOKEN_CREATION_DATE": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "VIDEO_SAVE_PATH": "",
            "TIME_TO_REFRESH": "3600",
        }
        self.save_preferences(preferences)
        return preferences

    def get_preferences(self):
        return self.db_handler.get_app_prefs()

    def save_preferences(self, prefs):
        self.db_handler.save_app_prefs(prefs)

    def delete_preferences(self):
        self.db_handler.delete_table()

    def start_task(self):
        if not self.running:
            self.running = True
            self._start_periodic_task()

    def stop_task(self):
        self.running = False
        if self.timer_thread:
            self.timer_thread.cancel()

    def _start_periodic_task(self):
        def task():
            if self.running:
                prefs = self.get_preferences()
                retries = 3
                backoff = 60  # Backoff time in seconds
                success = False

                for attempt in range(1, retries + 1):
                    try:
                        main(
                            prefs.get("MASTER_TOKEN", ""),
                            prefs.get("USERNAME", ""),
                            prefs.get("VIDEO_SAVE_PATH", ""),
                        )
                        success = True
                        break
                    except Exception as e:
                        logger.error(f"Attempt {attempt} failed: {e}. Retrying in {backoff} seconds.")
                        if attempt < retries:
                            remaining_backoff = backoff
                            while remaining_backoff > 0 and self.running:
                                time.sleep(0.5)
                                remaining_backoff -= 0.5

                if not success:
                    logger.error(f"All retries failed. Waiting for next refresh interval ({self.refresh_interval} seconds).")
                
                self.refresh_interval = int(prefs.get("TIME_TO_REFRESH", self.refresh_interval))
                if self.running:
                    self.timer_thread = threading.Timer(self.refresh_interval, task)
                    self.timer_thread.start()

        task()

    def run_console(self):
        print("Nest Clipper")
        print("-------------------")

        if not is_user_authed():
            self._prompt_for_credentials()

        print("\nStarting Nest Clipper...")
        self.start_task()

        def handle_exit(signum, frame):
            print("\nStopping Nest Clipper due to terminal closure or interruption...")
            self.stop_task()
            exit(0)

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, handle_exit)  # Ctrl+C
        signal.signal(signal.SIGTERM, handle_exit)  # Termination signal

        try:
            print("Nest Clipper is running. To stop, press Ctrl+C.")
            while True:
                time.sleep(0.5)  # Sleep in small increments to avoid busy-waiting
        except KeyboardInterrupt:
            handle_exit(None, None)

    def _prompt_for_credentials(self):
        authenticated = False

        while not authenticated:
            email = input("Please enter email linked to Nest devices: ").strip()
            app_password = input("Please enter the app password: ").strip()

            try:
                preferences = self.authenticate_user(email, app_password)
                video_save_path = input("Enter path to save Nest clips: ").strip()
                refresh_interval = input("Enter refresh interval in seconds (default=3600): ").strip()
                preferences["VIDEO_SAVE_PATH"] = video_save_path
                preferences["TIME_TO_REFRESH"] = refresh_interval or "3600"
                self.save_preferences(preferences)
                authenticated = True
                return preferences["MASTER_TOKEN"], email, video_save_path
            except Exception as e:
                print(f"Error: {e}. Please try again.\n")

def is_user_authed():
    return str(DatabaseHandler(get_db_path()).get_app_prefs().get("MASTER_TOKEN")).startswith("aas") # this should also check if master token is valid. not sure how to do that

def main(master_token, username, video_save_path):
    connection = Connection(master_token, username)
    nest_camera_devices = connection.get_nest_camera_devices()
    end_time = datetime.datetime.now() - datetime.timedelta(minutes=3)

    amount_of_new_clips_saved = 0

    print(f"Checking for new events as of {end_time}")
    print(f"Found Cameras: {[nest_device.device_name for nest_device in nest_camera_devices]}")
    for nest_device in nest_camera_devices:

        try:
            events = nest_device.get_events(
                end_time = end_time,
                duration_minutes = HOURS_TO_CHECK * 60
            )
        except Exception as e:
            logger.error(f"Failed to get events for {nest_device.device_name}: {e}")
            continue

        for event in events:
            try:
                video_data = nest_device.download_camera_event(event)
            except Exception as e:
                logger.error(f"Failed to download camera event for {event.event_id} from {nest_device.device_name}: {e}")
                continue

            event_start_time = event.start_time.astimezone()
            event_year = str(event_start_time.year)
            event_month = str(event_start_time.month)
            event_day = str(event_start_time.day)
            
            safe_filename = f"{event_start_time.strftime('%Y%m%dT%H%M%S%z')}.mp4"
            safe_filename_with_ext = os.path.join(video_save_path, event_year, event_month, event_day, nest_device.device_name, safe_filename)
            
            os.makedirs(os.path.dirname(safe_filename_with_ext), exist_ok=True)

            if not os.path.exists(safe_filename_with_ext):
                with open(safe_filename_with_ext, "wb") as f:
                    print(f"Saving video to {safe_filename_with_ext}")
                    amount_of_new_clips_saved += 1
                    f.write(video_data)

    print(f"Saved {amount_of_new_clips_saved} new clips\n\n")