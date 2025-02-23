import time
import board
import displayio
from adafruit_display_text import label
import terminalio
import wifi
import socketpool
import adafruit_ntp
import rtc
import secrets

def compute_yearday(year, month, day):
    """Compute the day of the year (1-366)."""
    month_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    # Check for leap year.
    if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)):
        month_days[1] = 29
    return sum(month_days[:month - 1]) + day

def is_dst(year, month, day, hour):
    """Determine if Daylight Saving Time (DST) is in effect for Chicago, IL.
       DST starts on the second Sunday in March at 2:00 AM,
       and ends on the first Sunday in November at 2:00 AM.
    """
    # Calculate DST start: second Sunday in March
    march_first = time.mktime((year, 3, 1, 0, 0, 0, 0, 0, 0))
    march_first_weekday = time.localtime(march_first).tm_wday  # Monday is 0
    # Find the first Sunday (0 = Monday, so Sunday is 6 or 0 depending on convention)
    first_sunday = 1 + ((6 - march_first_weekday) % 7)
    second_sunday = first_sunday + 7
    dst_start = time.mktime((year, 3, second_sunday, 2, 0, 0, 0, 0, 0))
    
    # Calculate DST end: first Sunday in November
    november_first = time.mktime((year, 11, 1, 0, 0, 0, 0, 0, 0))
    november_first_weekday = time.localtime(november_first).tm_wday
    first_sunday_nov = 1 + ((6 - november_first_weekday) % 7)
    dst_end = time.mktime((year, 11, first_sunday_nov, 2, 0, 0, 0, 0, 0))
    
    current = time.mktime((year, month, day, hour, 0, 0, 0, 0, 0))
    return dst_start <= current < dst_end

def connect_wifi(ssid, password):
    """Connect to WiFi and return the assigned IP address."""
    print("Connecting to WiFi...")
    wifi.radio.connect(ssid, password)
    ip_address = wifi.radio.ipv4_address
    print("Connected, IP address:", ip_address)
    return ip_address

def setup_time():
    """
    Get the UTC time via NTP, adjust it for Central Time (CST/CDT),
    and set the RTC accordingly.
    """
    pool = socketpool.SocketPool(wifi.radio)
    # Get UTC time from NTP
    ntp = adafruit_ntp.NTP(pool, tz_offset=0)
    ntp_time = ntp.datetime
    # Unpack the NTP time tuple: (year, month, day, hour, minute, second, subsecond, weekday)
    year = ntp_time[0]
    month = ntp_time[1]
    day = ntp_time[2]
    hour = ntp_time[3]
    minute = ntp_time[4]
    second = ntp_time[5]
    weekday = ntp_time[7]

    # Determine timezone offset based on DST for Chicago
    if is_dst(year, month, day, hour):
        tz_offset = -5 * 3600  # CDT (UTC-5)
    else:
        tz_offset = -6 * 3600  # CST (UTC-6)

    # Adjust the time using mktime (returns seconds since epoch)
    adjusted_secs = time.mktime((year, month, day, hour, minute, second, weekday, 0, 0)) + tz_offset
    adjusted_time = time.localtime(adjusted_secs)

    # Set the RTC using a 9-tuple:
    # (year, month, day, hour, minute, second, weekday, yearday, isdst)
    rtc.RTC().datetime = (
        adjusted_time.tm_year,
        adjusted_time.tm_mon,
        adjusted_time.tm_mday,
        adjusted_time.tm_hour,
        adjusted_time.tm_min,
        adjusted_time.tm_sec,
        adjusted_time.tm_wday,
        compute_yearday(adjusted_time.tm_year, adjusted_time.tm_mon, adjusted_time.tm_mday),
        -1  # isdst is not used
    )

def create_display(ip_address):
    """
    Create the display setup: a white background,
    greeting label, IP address label, and a time label.
    Returns the display object and the time label (to update later).
    """
    display = board.DISPLAY
    splash = displayio.Group()
    display.root_group = splash

    # White background
    background_bitmap = displayio.Bitmap(display.width, display.height, 1)
    background_palette = displayio.Palette(1)
    background_palette[0] = 0xFFFFFF  # White
    background_sprite = displayio.TileGrid(background_bitmap, pixel_shader=background_palette)
    splash.append(background_sprite)

    # Greeting label: "Hello, MagTag!"
    greeting = label.Label(terminalio.FONT, text="Hello, MagTag!", color=0x000000)
    greeting.scale = 2
    greeting.anchor_point = (0.5, 0.5)
    greeting.anchored_position = (display.width // 2, display.height // 2 - 30)
    splash.append(greeting)

    # IP address label below the greeting
    ip_label = label.Label(terminalio.FONT, text="IP: " + str(ip_address), color=0x000000)
    ip_label.scale = 2
    ip_label.anchor_point = (0.5, 0.5)
    ip_label.anchored_position = (display.width // 2, display.height // 2)
    splash.append(ip_label)

    # Time label below the IP address label
    time_label = label.Label(terminalio.FONT, text="Time: --:--", color=0x000000)
    time_label.scale = 2
    time_label.anchor_point = (0.5, 0.5)
    time_label.anchored_position = (display.width // 2, display.height // 2 + 30)
    splash.append(time_label)

    display.refresh()
    return display, time_label

def update_display_time(display, time_label):
    """
    Update the time label on the display in 12-hour format with AM/PM,
    then refresh the display.
    """
    # rtc.RTC().datetime returns a 9-tuple:
    # (year, month, day, hour, minute, second, weekday, yearday, isdst)
    current_datetime = rtc.RTC().datetime
    hours_24 = current_datetime[3]
    minutes = current_datetime[4]

    # Convert 24-hour format to 12-hour format with AM/PM
    if hours_24 == 0:
        hours_12 = 12
        meridiem = "AM"
    elif hours_24 < 12:
        hours_12 = hours_24
        meridiem = "AM"
    elif hours_24 == 12:
        hours_12 = 12
        meridiem = "PM"
    else:
        hours_12 = hours_24 - 12
        meridiem = "PM"

    current_time_str = "{:02d}:{:02d} {}".format(hours_12, minutes, meridiem)
    time_label.text = "Time: " + current_time_str

    # Refresh the display; if "Refresh too soon", wait and retry.
    refreshed = False
    while not refreshed:
        try:
            display.refresh()
            refreshed = True
        except RuntimeError as e:
            if "Refresh too soon" in str(e):
                print("Refresh too soon; waiting 5 seconds before retrying.")
                time.sleep(5)
            else:
                raise e

def main():
    # WiFi credentials
    ssid = secrets.secrets["ssid"]
    password = secrets.secrets["password"]

    # Connect to WiFi and set up the time
    ip_address = connect_wifi(ssid, password)
    setup_time()

    # Create the display and get the time label reference
    display, time_label = create_display(ip_address)

    # Main loop: update the display time every minute
    while True:
        update_display_time(display, time_label)
        time.sleep(60)

# Run the main function
main()
