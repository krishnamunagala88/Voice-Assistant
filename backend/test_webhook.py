"""
Test script to verify the FastAPI webhook endpoint `/api/vapi-tool` locally.
"""
import os
os.environ["NO_GCE_CHECK"] = "true"

import requests
import datetime
import calendar_service


def test_webhook():
    print("=== Webhook Endpoint Test ===")
    
    # 1. Test check_available_slots
    tomorrow = (datetime.datetime.now(calendar_service.IST) + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"\n1. Testing check_available_slots via webhook for tomorrow ({tomorrow})...")
    
    payload_slots = {
        "message": {
            "type": "tool-call",
            "toolCalls": [
                {
                    "id": "call_test_slots_123",
                    "type": "function",
                    "function": {
                        "name": "check_available_slots",
                        "arguments": {
                            "department": "Tummy Tuck",
                            "date": tomorrow
                        }
                    }
                }
            ]
        }
    }
    
    try:
        resp = requests.post("http://localhost:8000/api/vapi-tool", json=payload_slots, timeout=10)
        print(f"Status Code: {resp.status_code}")
        print("Response payload:")
        print(resp.json())
        assert resp.status_code == 200, "Expected status code 200"
        print("[OK] check_available_slots webhook test passed!")
    except Exception as e:
        print(f"[FAIL] check_available_slots webhook test failed: {e}")
        return

    # 2. Test book_appointment
    print("\n2. Testing book_appointment via webhook...")
    payload_book = {
        "message": {
            "type": "tool-call",
            "toolCalls": [
                {
                    "id": "call_test_book_456",
                    "type": "function",
                    "function": {
                        "name": "book_appointment",
                        "arguments": {
                            "patient_name": "Webhook Test Patient",
                            "phone_number": "1234567890",
                            "department": "Tummy Tuck",
                            "doctor_name": "Dr. Arjun Handa",
                            "date": tomorrow,
                            "time": "11:30 AM"
                        }
                    }
                }
            ]
        }
    }

    
    try:
        resp = requests.post("http://localhost:8000/api/vapi-tool", json=payload_book, timeout=10)
        print(f"Status Code: {resp.status_code}")
        resp_data = resp.json()
        print("Response payload:")
        print(resp_data)
        assert resp.status_code == 200, "Expected status code 200"
        
        # Verify success and perform clean-up
        results = resp_data.get("results", [])
        if results and "confirmed" in results[0].get("result", "").lower():
            print("[OK] book_appointment webhook test passed!")
            
            # Find the booked event to clean up
            print("\n3. Cleaning up test event from calendar...")
            client = calendar_service.get_calendar_client()
            time_min = datetime.datetime.combine(
                calendar_service.parse_date(tomorrow), datetime.time(0, 0, 0), tzinfo=calendar_service.IST
            ).isoformat()
            time_max = datetime.datetime.combine(
                calendar_service.parse_date(tomorrow), datetime.time(23, 59, 59), tzinfo=calendar_service.IST
            ).isoformat()
            
            events_res = client.events().list(
                calendarId=calendar_service.GOOGLE_CALENDAR_ID,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True
            ).execute()
            
            # Find matching event
            for event in events_res.get("items", []):
                if "Webhook Test Patient" in event.get("summary", ""):
                    event_id = event.get("id")
                    client.events().delete(
                        calendarId=calendar_service.GOOGLE_CALENDAR_ID,
                        eventId=event_id
                    ).execute()
                    print(f"[OK] Successfully deleted test event: {event_id}")
                    break
        else:
            print("[FAIL] book_appointment webhook test failed: unexpected result content")
    except Exception as e:
        print(f"[FAIL] book_appointment webhook test failed: {e}")


if __name__ == "__main__":
    test_webhook()
