"""
Calendar Service — Interfaces with Google Calendar API using Service Account credentials.
Handles slot checking (conflict detection) and appointment booking in the clinic's local timezone (Asia/Kolkata).
"""
import datetime
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import GOOGLE_CALENDAR_CREDENTIALS, GOOGLE_CALENDAR_ID

logger = logging.getLogger(__name__)

# Constants
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# Suppress regional access boundary metadata checks and oauth log noise (benign warnings)
logging.getLogger("google").setLevel(logging.ERROR)
logging.getLogger("google.auth").setLevel(logging.ERROR)
logging.getLogger("google.auth._regional_access_boundary_utils").setLevel(logging.ERROR)
logging.getLogger("googleapiclient").setLevel(logging.ERROR)


DEPT_TO_DOCTOR = {
    # Dr. Arjun Handa's Specialties & Procedures
    "tummy tuck": "Dr. Arjun Handa",
    "abdominoplasty": "Dr. Arjun Handa",
    "liposuction": "Dr. Arjun Handa",
    "body contouring": "Dr. Arjun Handa",
    "breast surgery": "Dr. Arjun Handa",
    "breast augmentation": "Dr. Arjun Handa",
    "gynecomastia": "Dr. Arjun Handa",
    "cosmetic surgery": "Dr. Arjun Handa",
    "general surgery": "Dr. Arjun Handa",
    
    # Dr. Shruti Handa's Specialties & Procedures
    "rhinoplasty": "Dr. Shruti Handa",
    "nose surgery": "Dr. Shruti Handa",
    "facial aesthetics": "Dr. Shruti Handa",
    "lip surgery": "Dr. Shruti Handa",
    "lip reduction": "Dr. Shruti Handa",
    "lip fillers": "Dr. Shruti Handa",
    "fillers": "Dr. Shruti Handa",
    "non-invasive": "Dr. Shruti Handa",
    "hydrafacial": "Dr. Shruti Handa",
    "microneedling": "Dr. Shruti Handa",
    "ent": "Dr. Shruti Handa",
    "ear nose throat": "Dr. Shruti Handa",
    "dermatology": "Dr. Shruti Handa"
}


def get_calendar_client():
    """Build and return a fresh Google Calendar API client service."""
    try:
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_CALENDAR_CREDENTIALS,
            scopes=["https://www.googleapis.com/auth/calendar"]
        )
        return build("calendar", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        logger.error(f"Failed to create Google Calendar client: {e}", exc_info=True)
        raise RuntimeError(f"Google Calendar initialization failed: {e}")



def parse_date(date_str: str) -> datetime.date:
    """Parse a date string in various formats into a datetime.date object."""
    date_str = date_str.strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    # Handle ISO timestamps or dates with time (e.g. 2026-06-21T00:00:00 or 2026-06-21 10:00)
    try:
        iso_part = date_str.split("T")[0].split(" ")[0]
        return datetime.datetime.strptime(iso_part, "%Y-%m-%d").date()
    except Exception:
        raise ValueError(f"Unable to parse date string: {date_str}")

def parse_time(time_str: str) -> datetime.time:
    """Parse a time string (12-hour or 24-hour) into a datetime.time object."""
    time_str = time_str.strip().upper()
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M", "%H:%M:%S"):
        try:
            return datetime.datetime.strptime(time_str, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Unable to parse time string: {time_str}")

def check_available_slots(date_str: str, department: str = "") -> list[str]:
    """
    Find available 30-minute appointment slots for the given date.
    Excludes past times if checking today, and matches against existing calendar events.
    """
    try:
        date_obj = parse_date(date_str)
    except ValueError as e:
        logger.error(f"Invalid date format: {date_str}. Error: {e}")
        return []

    # 1. Determine working hours for the clinic
    # Monday (0) to Friday (4): 9:00 AM – 7:00 PM (09:00 - 19:00)
    # Saturday (5): 9:00 AM – 4:00 PM (09:00 - 16:00)
    # Sunday (6): 10:00 AM – 1:00 PM (10:00 - 13:00)
    weekday = date_obj.weekday()
    if weekday < 5:
        start_hour, end_hour = 9, 19
    elif weekday == 5:
        start_hour, end_hour = 9, 16
    else:
        start_hour, end_hour = 10, 13

    # 2. Query existing events for this day
    # Run the query from the beginning to the end of the day in IST
    time_min = datetime.datetime.combine(date_obj, datetime.time(0, 0, 0), tzinfo=IST).isoformat()
    time_max = datetime.datetime.combine(date_obj, datetime.time(23, 59, 59), tzinfo=IST).isoformat()

    try:
        client = get_calendar_client()
        events_result = client.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        events = events_result.get("items", [])
    except Exception as e:
        logger.error(f"Error calling Google Calendar API: {e}", exc_info=True)
        # Fall back to returning empty slots or raising
        return []

    # 3. Parse existing event ranges
    parsed_events = []
    for event in events:
        start = event.get("start", {})
        end = event.get("end", {})
        start_dt = start.get("dateTime") or start.get("date")
        end_dt = end.get("dateTime") or end.get("date")

        if not start_dt or not end_dt:
            continue

        try:
            if "dateTime" not in start:
                # All-day event covers the whole day in local timezone
                e_start = datetime.datetime.strptime(start_dt, "%Y-%m-%d").replace(tzinfo=IST)
                e_end = datetime.datetime.strptime(end_dt, "%Y-%m-%d").replace(tzinfo=IST)
            else:
                e_start = datetime.datetime.fromisoformat(start_dt.replace("Z", "+00:00")).astimezone(IST)
                e_end = datetime.datetime.fromisoformat(end_dt.replace("Z", "+00:00")).astimezone(IST)
            parsed_events.append((e_start, e_end))
        except Exception as pe:
            logger.error(f"Failed to parse event boundary: {pe}")

    # 4. Generate 30-minute slots and check availability
    now_ist = datetime.datetime.now(IST)
    available_slots = []

    current_time = datetime.datetime.combine(date_obj, datetime.time(start_hour, 0), tzinfo=IST)
    end_limit = datetime.datetime.combine(date_obj, datetime.time(end_hour, 0), tzinfo=IST)

    while current_time + datetime.timedelta(minutes=30) <= end_limit:
        slot_start = current_time
        slot_end = current_time + datetime.timedelta(minutes=30)

        # Skip past times if checking today
        if slot_start < now_ist:
            current_time = slot_end
            continue

        # Check for overlap with existing events
        is_busy = False
        for e_start, e_end in parsed_events:
            # Overlap occurs if slot start is before event end AND slot end is after event start
            if slot_start < e_end and slot_end > e_start:
                is_busy = True
                break

        if not is_busy:
            available_slots.append(slot_start.strftime("%I:%M %p"))

        current_time = slot_end

    return available_slots

def book_appointment(
    patient_name: str,
    phone_number: str,
    department: str,
    doctor_name: str = "",
    date_str: str = "",
    time_str: str = ""
) -> dict:
    """
    Create a new calendar event for the appointment.
    """
    try:
        date_obj = parse_date(date_str)
        time_obj = parse_time(time_str)
    except ValueError as e:
        logger.error(f"Error parsing date/time parameters: {e}")
        return {"status": "error", "message": str(e)}

    # Resolve doctor name if not provided
    if not doctor_name:
        dept_key = department.lower().strip()
        doctor_name = DEPT_TO_DOCTOR.get(dept_key, "Clinic Physician")

    # Combine start date & time in IST
    start_dt = datetime.datetime.combine(date_obj, time_obj, tzinfo=IST)
    end_dt = start_dt + datetime.timedelta(minutes=30)

    # Prepare Google Calendar Event resource
    event_payload = {
        "summary": f"Appointment: {patient_name} - {doctor_name} ({department})",
        "description": (
            f"Patient: {patient_name}\n"
            f"Phone Number: {phone_number}\n"
            f"Department: {department}\n"
            f"Doctor: {doctor_name}\n"
            f"Status: Booked via AI Voice Receptionist"
        ),
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
        "reminders": {
            "useDefault": True,
        }
    }

    try:
        client = get_calendar_client()
        event = client.events().insert(
            calendarId=GOOGLE_CALENDAR_ID,
            body=event_payload
        ).execute()

        logger.info(f"Successfully booked appointment: {event.get('htmlLink')}")
        return {
            "status": "success",
            "message": f"Appointment confirmed with {doctor_name} on {date_str} at {time_str}.",
            "eventId": event.get("id"),
            "htmlLink": event.get("htmlLink")
        }
    except Exception as e:
        logger.error(f"Error inserting event to Google Calendar: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Could not save appointment to calendar. Details: {e}"
        }
