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
                main(
                    prefs.get("MASTER_TOKEN", ""),
                    prefs.get("USERNAME", ""),
                    prefs.get("VIDEO_SAVE_PATH", ""),
                )
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

        print("\nStarting clipper...")
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
                remaining_time = self.refresh_interval
                while remaining_time > 0:
                    time.sleep(min(0.5, remaining_time))
                    remaining_time -= 0.5
        except KeyboardInterrupt:
            # Redundant cleanup just in case
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
    logger.info("Getting Camera Devices")
    nest_camera_devices = connection.get_nest_camera_devices()
    end_time = datetime.datetime.now() - datetime.timedelta(minutes=3)

    amount_of_new_clips_saved = 0

    print(f"Checking for new events as of {end_time}")
    print(f"Found Cameras: {[nest_device.device_name for nest_device in nest_camera_devices]}")
    for nest_device in nest_camera_devices:

        events = nest_device.get_events(
            end_time = end_time,

            # SOMETHING WEIRD GOING ON HERE MAYBE. TOWARDS THE END OF HOURS, NOT ALL EXPECTED EVENTS ARE FOUND MAYBE.
            duration_minutes = HOURS_TO_CHECK * 60
        )

        for event in events:
            video_data = nest_device.download_camera_event(event)
            event_year = str(event.start_time.date().year)
            event_month = str(event.start_time.date().month)
            event_day = str(event.start_time.date().day)
            safe_filename = f"{event.start_time.astimezone().strftime('%Y%m%dT%H%M%S%z')}.mp4"
            
            safe_filename_with_ext = os.path.join(video_save_path, event_year, event_month, event_day, nest_device.device_name, safe_filename)
            os.makedirs(os.path.dirname(safe_filename_with_ext), exist_ok=True)

            if not os.path.exists(safe_filename_with_ext):
                with open(safe_filename_with_ext, "wb") as f:
                    print(f"Saving video to {safe_filename_with_ext}")
                    amount_of_new_clips_saved += 1
                    f.write(video_data)

    print(f"Saved {amount_of_new_clips_saved} new clips\n\n")