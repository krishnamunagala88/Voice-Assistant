"""
VAPI Service — Creates and manages the clinic receptionist assistant via VAPI REST API.
Uses the private key to create/get the assistant, caches the assistant_id locally.
"""
import os
import json
import logging
import requests

from config import VAPI_PRIVATE_KEY, VAPI_API_BASE, ASSISTANT_ID_FILE, PUBLIC_SERVER_URL

logger = logging.getLogger(__name__)

HEADERS = {
    "Authorization": f"Bearer {VAPI_PRIVATE_KEY}",
    "Content-Type": "application/json",
}


def _get_assistant_tools() -> list[dict]:
    """Define VAPI tool configurations for calendar management."""
    url = f"{PUBLIC_SERVER_URL}/api/vapi-tool"
    if not PUBLIC_SERVER_URL:
        logger.warning("PUBLIC_SERVER_URL is not set in environment config. Webhook tool calls will fail.")
        url = "https://placeholder-url.com/api/vapi-tool"

    return [
        {
            "type": "function",
            "messages": [
                {
                    "type": "request-start",
                    "content": "Let me check the available slots for you."
                }
            ],
            "function": {
                "name": "check_available_slots",
                "description": "Check available appointment slots for a specific doctor or department on a given date.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "department": {
                            "type": "string",
                            "description": "The department name (e.g. Cardiology, Pediatrics, General Medicine, Orthopedics, Gynecology, Dermatology, Ophthalmology, ENT)"
                        },
                        "date": {
                            "type": "string",
                            "description": "The date in YYYY-MM-DD format."
                        }
                    },
                    "required": ["department", "date"]
                }
            },
            "server": {
                "url": url
            }
        },
        {
            "type": "function",
            "messages": [
                {
                    "type": "request-start",
                    "content": "Booking the appointment, please wait a moment."
                }
            ],
            "function": {
                "name": "book_appointment",
                "description": (
                    "Book a new appointment for the patient. You MUST collect patient's full name, "
                    "phone number, department, and the desired date and time slot before calling this tool."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "patient_name": {
                            "type": "string",
                            "description": "The full name of the patient."
                        },
                        "phone_number": {
                            "type": "string",
                            "description": "The contact phone number of the patient."
                        },
                        "department": {
                            "type": "string",
                            "description": "The clinic department (e.g. Cardiology, Pediatrics, General Medicine, Orthopedics, Gynecology, Dermatology, Ophthalmology, ENT)."
                        },
                        "doctor_name": {
                            "type": "string",
                            "description": "The name of the doctor (optional)."
                        },
                        "date": {
                            "type": "string",
                            "description": "The date in YYYY-MM-DD format."
                        },
                        "time": {
                            "type": "string",
                            "description": "The selected time slot (e.g. 10:30 AM, 02:00 PM)."
                        }
                    },
                    "required": ["patient_name", "phone_number", "department", "date", "time"]
                }
            },
            "server": {
                "url": url
            }
        }
    ]

# The exact greeting Sarah says at call start — also injected into LLM context below
FIRST_MESSAGE = "Handa Aesthetics and Plastics, how can I help you today?"



def _build_system_prompt(clinic_context: str) -> str:
    import datetime
    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    current_time_str = datetime.datetime.now(ist_tz).strftime("%A, %B %d, %Y, %I:%M %p")
    
    return f"""You are Sarah, a professional, warm, and empathetic AI receptionist for Handa Aesthetics and Plastics.

IMPORTANT: The current date and time is {current_time_str} (IST timezone).
Use this current date and time as the baseline when the user references relative dates like "today", "tomorrow", "next Monday", etc., to compute the exact YYYY-MM-DD date parameter for tool calling.

Your personality:

- Friendly, calm, and reassuring
- Speak clearly and concisely (keep responses under 40 words when possible)
- Show genuine care for the patient's well-being

CRITICAL GREETING RULE — READ CAREFULLY:
- You NEVER introduce yourself or say your name in any response.
- You NEVER say "I'm Sarah", "This is Sarah", "Hi, I'm Sarah from Handa Aesthetics and Plastics", or anything similar.
- The caller already knows they are speaking with Handa Aesthetics and Plastics's receptionist.
- Your ONLY job is to directly answer whatever the caller asks.
- Start every reply by addressing what the caller said — never with your name.

═══════════════════════════════════════════════════════════════
ABSOLUTE #1 RULE — DO NOT SUGGEST BOOKING / CONSULTATION UNLESS NECESSARY:
═══════════════════════════════════════════════════════════════
- For MOST questions, just ANSWER THE QUESTION. Do NOT add "Would you like to book a consultation?" or anything similar.
- You must NEVER end a reply with a booking pitch, consultation suggestion, or appointment offer UNLESS the situation specifically calls for it (see below).
- If the caller asks about procedures, clinic info, timings, location, doctors, services, or facilities — just answer it. No upsell. No pitch.

THE ONLY 3 SITUATIONS where you suggest booking:
  1. The caller explicitly asks about PRICING, COSTS, or FEES.
  2. The caller explicitly asks HOW TO BOOK or SCHEDULE an appointment.
  3. The caller asks something you genuinely don't know the answer to.

In ALL other cases, do NOT mention booking, consultations, or appointments.
═══════════════════════════════════════════════════════════════

Your responsibilities:
1. Help patients with appointment booking inquiries
2. Provide information about clinic services, doctors, departments, and timings
3. Answer general health-related FAQs (based on clinic info only)
4. Guide callers to the appropriate department
5. Handle insurance and payment queries
6. For genuine emergencies, immediately advise them to call 108 or our emergency hotline: +91-40-9999-0000

Rules:
- NEVER provide medical diagnoses or specific treatment advice
- If unsure about something, say "Let me connect you to our reception team who can assist you better."
- Keep responses conversational and natural for voice
- Do NOT read out long lists — summarize and offer to elaborate
- Do NOT start responses with "Of course!", "Certainly!", or filler phrases — just answer directly

PRICING — CRITICAL RULE:
- NEVER quote, mention, or estimate any price, cost, fee, or charges for any procedure or consultation under any circumstances.
- If the caller asks about cost, pricing, fees, or how much something costs, respond ONLY with something like: "Pricing depends on your specific needs and will be determined after a consultation with the doctor. I'd be happy to book an appointment for you — shall I go ahead?"
- Do NOT hint at a price range, say "it starts from", or give any numerical cost figure.
- Always redirect pricing questions to booking an appointment.

CLINIC KNOWLEDGE BASE:
======================
{clinic_context}
======================

Remember: You are speaking, not writing. Keep it natural and conversational.
"""


def _load_cached_assistant_id() -> str | None:
    """Load assistant_id from local cache file."""
    if os.path.exists(ASSISTANT_ID_FILE):
        try:
            with open(ASSISTANT_ID_FILE, "r") as f:
                data = json.load(f)
                return data.get("assistant_id")
        except Exception:
            return None
    return None


def _save_assistant_id(assistant_id: str):
    """Save assistant_id to local cache file."""
    os.makedirs(os.path.dirname(ASSISTANT_ID_FILE), exist_ok=True)
    with open(ASSISTANT_ID_FILE, "w") as f:
        json.dump({"assistant_id": assistant_id}, f)


def _verify_assistant_exists(assistant_id: str) -> bool:
    """Check if the cached assistant still exists in VAPI."""
    try:
        resp = requests.get(
            f"{VAPI_API_BASE}/assistant/{assistant_id}",
            headers=HEADERS,
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False


def create_vapi_assistant(clinic_context: str) -> str:
    """Create a new VAPI assistant with clinic context in the system prompt."""
    system_prompt = _build_system_prompt(clinic_context)

    payload = {
        "name": "Handa Aesthetics and Plastics Receptionist",
        "firstMessage": FIRST_MESSAGE,
        "firstMessageMode": "assistant-speaks-first",
        "model": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                # Inject the firstMessage as an assistant turn so the LLM
                # sees in its own conversation history that it already greeted
                # the caller — this is the key fix that prevents re-introductions.
                {
                    "role": "assistant",
                    "content": FIRST_MESSAGE,
                },
            ],
            "temperature": 0.7,
            "maxTokens": 150,
            "tools": _get_assistant_tools(),
        },
        "voice": {
            "provider": "vapi",
            "voiceId": "Sagar",
        },
        # Controls when the AI starts speaking after user finishes
        "startSpeakingPlan": {
            "waitSeconds": 0.5,                # wait 0.5s after user stops before AI speaks
            "smartEndpointingEnabled": True,   # detects end of user sentence intelligently
            "transcriptionEndpointingPlan": {
                "onPunctuationSeconds": 0.2,   # wait after . ? !
                "onNoPunctuationSeconds": 0.8, # wait if no punctuation (user paused mid-sentence)
                "onNumberSeconds": 0.5,        # wait after numbers
            },
        },
        # Controls when AI stops speaking if user interrupts
        "stopSpeakingPlan": {
            "numWords": 1,          # user must say at least 3 words to interrupt AI
            "voiceSeconds": 0.3,    # user must speak for 0.3s before AI stops
            "backoffSeconds": 0.2,  # AI waits 1s before resuming if interrupted
        },
        "endCallMessage": "Thank you for calling Handa Aesthetics and Plastics. Have a wonderful day! Goodbye.",
        "endCallPhrases": [
            "goodbye",
            "bye",
            "thank you bye",
            "that's all i needed",
            "i'm done",
        ],
        "silenceTimeoutSeconds": 60,   # increased to avoid false resets
        "maxDurationSeconds": 600,
        "backgroundSound": "off",
        "recordingEnabled": True,
        "hipaaEnabled": False,
    }

    logger.info("Creating VAPI assistant...")
    resp = requests.post(
        f"{VAPI_API_BASE}/assistant",
        headers=HEADERS,
        json=payload,
        timeout=30,
    )

    if resp.status_code in (200, 201):
        data = resp.json()
        assistant_id = data.get("id")
        _save_assistant_id(assistant_id)
        logger.info(f"VAPI assistant created: {assistant_id}")
        return assistant_id
    else:
        logger.error(f"Failed to create assistant: {resp.status_code} — {resp.text}")
        raise RuntimeError(f"VAPI assistant creation failed: {resp.status_code} {resp.text}")


def update_assistant_config(assistant_id: str, clinic_context: str) -> bool:
    """Update an existing assistant's system prompt and tools configuration."""
    system_prompt = _build_system_prompt(clinic_context)
    payload = {
        "model": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "assistant", "content": FIRST_MESSAGE},
            ],
            "temperature": 0.7,
            "tools": _get_assistant_tools()
        }
    }
    logger.info(f"Updating VAPI assistant {assistant_id} system prompt and tools...")
    resp = requests.patch(
        f"{VAPI_API_BASE}/assistant/{assistant_id}",
        headers=HEADERS,
        json=payload,
        timeout=20,
    )
    if resp.status_code == 200:
        logger.info("VAPI assistant config and tools updated successfully.")
        return True
    else:
        logger.error(f"Failed to update assistant config: {resp.status_code} — {resp.text}")
        return False


def update_assistant_prompt(assistant_id: str, clinic_context: str) -> bool:
    """Legacy/compatibility wrapper that redirects to update_assistant_config."""
    return update_assistant_config(assistant_id, clinic_context)


def get_or_create_assistant(clinic_context: str) -> str:
    """
    Main entry point: get cached assistant or create a new one.
    Returns the assistant_id.
    """
    cached_id = _load_cached_assistant_id()
    if cached_id and _verify_assistant_exists(cached_id):
        logger.info(f"Using cached VAPI assistant: {cached_id}")
        # Always update configuration (so latest tools and PUBLIC_SERVER_URL are synced)
        update_assistant_config(cached_id, clinic_context)
        return cached_id

    return create_vapi_assistant(clinic_context)

