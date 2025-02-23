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

# Month names for formatting the date
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

def compute_yearday(year, month, day):
    """Compute the day of the year (1-366)."""
    month_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)):
        month_days[1] = 29
    return sum(month_days[:month - 1]) + day

def is_dst(year, month, day, hour):
    """Determine if Daylight Saving Time (DST) is in effect for Chicago, IL."""
    march_first = time.mktime((year, 3, 1, 0, 0, 0, 0, 0, 0))
    march_first_weekday = time.localtime(march_first).tm_wday
    first_sunday = 1 + ((6 - march_first_weekday) % 7)
    second_sunday = first_sunday + 7
    dst_start = time.mktime((year, 3, second_sunday, 2, 0, 0, 0, 0, 0))

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
    """Get the UTC time via NTP, adjust it for Central Time (CST/CDT), and set the RTC."""
    pool = socketpool.SocketPool(wifi.radio)
    ntp = adafruit_ntp.NTP(pool, tz_offset=0)

    # Get NTP time, unpack while safely handling extra values
    ntp_time = ntp.datetime
    year, month, day, hour, minute, second, _, weekday, *_ = ntp_time  # Fixed unpacking

    # Adjust timezone offset based on DST
    tz_offset = -5 * 3600 if is_dst(year, month, day, hour) else -6 * 3600
    adjusted_secs = time.mktime((year, month, day, hour, minute, second, weekday, 0, 0)) + tz_offset
    adjusted_time = time.localtime(adjusted_secs)

    rtc.RTC().datetime = (
        adjusted_time.tm_year,
        adjusted_time.tm_mon,
        adjusted_time.tm_mday,
        adjusted_time.tm_hour,
        adjusted_time.tm_min,
        adjusted_time.tm_sec,
        adjusted_time.tm_wday,
        compute_yearday(adjusted_time.tm_year, adjusted_time.tm_mon, adjusted_time.tm_mday),
        -1
    )

def create_display(ip_address):
    """Create the display and return display object along with label references."""
    display = board.DISPLAY
    splash = displayio.Group()
    display.root_group = splash

    background_bitmap = displayio.Bitmap(display.width, display.height, 1)
    background_palette = displayio.Palette(1)
    background_palette[0] = 0xFFFFFF
    background_sprite = displayio.TileGrid(background_bitmap, pixel_shader=background_palette)
    splash.append(background_sprite)

    greeting = label.Label(terminalio.FONT, text="Hello, MagTag!", color=0x000000)
    greeting.scale = 2
    greeting.anchor_point = (0.5, 0.5)
    greeting.anchored_position = (display.width // 2, display.height // 2 - 40)
    splash.append(greeting)

    ip_label = label.Label(terminalio.FONT, text="IP: " + str(ip_address), color=0x000000)
    ip_label.scale = 2
    ip_label.anchor_point = (0.5, 0.5)
    ip_label.anchored_position = (display.width // 2, display.height // 2 - 10)
    splash.append(ip_label)

    date_label = label.Label(terminalio.FONT, text="Date: --- --, ----", color=0x000000)
    date_label.scale = 2
    date_label.anchor_point = (0.5, 0.5)
    date_label.anchored_position = (display.width // 2, display.height // 2 + 20)
    splash.append(date_label)

    time_label = label.Label(terminalio.FONT, text="Time: --:--", color=0x000000)
    time_label.scale = 2
    time_label.anchor_point = (0.5, 0.5)
    time_label.anchored_position = (display.width // 2, display.height // 2 + 50)
    splash.append(time_label)

    display.refresh()
    return display, date_label, time_label

def update_display_time(display, date_label, time_label):
    """Update the date and time labels on the display."""
    current_datetime = rtc.RTC().datetime
    year, month, day, hour, minute = current_datetime[0], current_datetime[1], current_datetime[2], current_datetime[3], current_datetime[4]

    month_name = MONTH_NAMES[month - 1]
    date_label.text = "Date: {}, {} {}".format(month_name, day, year)

    if hour == 0:
        hours_12 = 12
        meridiem = "AM"
    elif hour < 12:
        hours_12 = hour
        meridiem = "AM"
    elif hour == 12:
        hours_12 = 12
        meridiem = "PM"
    else:
        hours_12 = hour - 12
        meridiem = "PM"

    time_label.text = "Time: {:02d}:{:02d} {}".format(hours_12, minute, meridiem)

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
    ssid = secrets.secrets["ssid"]
    password = secrets.secrets["password"]

    ip_address = connect_wifi(ssid, password)
    setup_time()

    display, date_label, time_label = create_display(ip_address)

    while True:
        update_display_time(display, date_label, time_label)
        time.sleep(60)

main()
