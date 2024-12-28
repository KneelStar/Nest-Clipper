from app_prefs_database import DatabaseHandler, get_db_path
from tools import logger
from auth_wrapper import Connection
import pytz
import os
import datetime

HOURS_TO_CHECK = 12

def main(MASTER_TOKEN, USERNAME, VIDEO_SAVE_PATH):
    connection = Connection(MASTER_TOKEN, USERNAME)

    logger.info("Getting Camera Devices")
    nest_camera_devices = connection.get_nest_camera_devices()
    
    for nest_device in nest_camera_devices:
        # Get all the events
        events = nest_device.get_events(
            end_time = pytz.timezone("US/Central").localize(datetime.datetime.now()),
            
            # SOMETHING WEIRD GOING ON HERE. TOWARDS THE END OF HOURS, NO EVENTS ARE FOUND.
            duration_minutes= HOURS_TO_CHECK * 60 
        )
        
        print(('Events for ' + nest_device.device_name + ': '), events)
        for event in events:
            video_data = nest_device.download_camera_event(event)
            
            event_year = str(event.start_time.date().year)
            event_month = str(event.start_time.date().month)
            event_day = str(event.start_time.date().day)
            safe_filename = f"{event.start_time.astimezone().strftime('%Y%m%dT%H%M%S%z')}.mp4"
            
            safe_filename_with_ext = os.path.join(VIDEO_SAVE_PATH, event_year, event_month, event_day, safe_filename)            
            os.makedirs(os.path.dirname(safe_filename_with_ext), exist_ok=True)

            if not os.path.exists(safe_filename_with_ext):
                with open(safe_filename_with_ext, 'wb') as f:
                    print(f"Saving video to {safe_filename_with_ext}")
                    f.write(video_data)

if __name__ == "__main__":
    print("Nest Clipper")
    print("-------------------")
    print("\nThis will only run once")

    master_token = input("Please enter master token: ")
    email = input("Please enter email that is linked to Nest devices: ")
    video_save_path = input("Please enter path to store Nest clips: ")

    main(master_token, email, video_save_path)