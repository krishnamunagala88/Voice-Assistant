"""
Test script for Google Calendar service integration.
"""
import os
os.environ["NO_GCE_CHECK"] = "true"

import logging
import datetime
import calendar_service


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_tests():
    print("=== Google Calendar Integration Test ===")
    
    # 1. Test get_calendar_client
    print("\n1. Testing Google Calendar Client Connection...")
    try:
        client = calendar_service.get_calendar_client()
        print("[OK] Successfully built Google Calendar API client!")
    except Exception as e:
        print(f"[FAIL] Connection failed: {e}")
        return

    # 2. Test check_available_slots
    tomorrow = (datetime.datetime.now(calendar_service.IST) + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"\n2. Checking available slots for tomorrow ({tomorrow})...")
    try:
        slots = calendar_service.check_available_slots(tomorrow, "Cardiology")
        print(f"[OK] Found {len(slots)} available slots:")
        print(slots[:10], "... and more" if len(slots) > 10 else "")
    except Exception as e:
        print(f"[FAIL] Failed to check available slots: {e}")
        return

    # 3. Test book_appointment
    print("\n3. Testing booking a temporary appointment...")
    try:
        book_res = calendar_service.book_appointment(
            patient_name="Test Patient (AI)",
            phone_number="9876543210",
            department="Tummy Tuck",
            doctor_name="Dr. Arjun Handa",
            date_str=tomorrow,
            time_str="11:30 AM"
        )

        print("Response received from book_appointment:")
        print(book_res)
        
        if book_res.get("status") == "success":
            print("[OK] Successfully booked test appointment!")
            event_id = book_res.get("eventId")
            
            # 4. Clean up / Delete the test event
            print("\n4. Cleaning up / deleting the test appointment...")
            try:
                client.events().delete(
                    calendarId=calendar_service.GOOGLE_CALENDAR_ID,
                    eventId=event_id
                ).execute()
                print("[OK] Successfully deleted test appointment event!")
            except Exception as de:
                print(f"[WARN] Clean-up failed to delete event {event_id}: {de}")
        else:
            print("[FAIL] Booking failed!")
    except Exception as e:
        print(f"[FAIL] Booking process encountered an error: {e}")


if __name__ == "__main__":
    run_tests()
