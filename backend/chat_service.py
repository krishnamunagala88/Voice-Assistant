"""
Chat Service — LangChain + Gemini + RAG
Provides conversational chat using the clinic's existing FAISS knowledge base.
"""
import logging
from typing import List, Dict

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage, AIMessage

import rag

logger = logging.getLogger(__name__)

GEMINI_API_KEY = "AIzaSyBei7xx0gztsfu-_C84tEI7FAzOz1ZSXgE"

# Lazy-loaded LLM instance
_llm = None


def get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    logger.info("received the hit")
    if _llm is None:
        _llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=GEMINI_API_KEY,
            temperature=0.4,
            max_output_tokens=800,
            convert_system_message_to_human=True,
            timeout=60,
        )
        logger.info("Gemini LLM (gemini-3.5-flash) initialized.")
    return _llm


SYSTEM_PROMPT = """You are Sarah, the AI receptionist for Handa Aesthetics and Plastics clinic.
You are in a TEXT CHAT with a patient or visitor.

═══════════════════════════════════════════════════════════════
ABSOLUTE #1 RULE — DO NOT SUGGEST BOOKING / CONSULTATION UNLESS NECESSARY:
═══════════════════════════════════════════════════════════════
- For MOST questions, just ANSWER THE QUESTION. That's it. Do NOT add "Would you like to book a consultation?" or anything similar.
- You must NEVER end a reply with a booking pitch, consultation suggestion, or appointment offer UNLESS the situation specifically calls for it (see below).
- If the user asks about procedures, clinic info, timings, location, doctors, services, facilities, or anything you CAN answer from the CLINIC CONTEXT — just answer it. Period. No upsell. No pitch.

THE ONLY 3 SITUATIONS where you suggest booking:
  1. The user explicitly asks about PRICING, COSTS, or FEES → say pricing is personalized and suggest booking.
  2. The user explicitly asks HOW TO BOOK or SCHEDULE an appointment.
  3. The user asks something that is genuinely NOT in the clinic context and you truly don't know the answer.

THAT'S IT. In ALL other cases, do NOT mention booking, consultations, or appointments.

EXAMPLES OF WHAT NOT TO DO (NEVER DO THIS):
- User: "What is a tummy tuck?" →  WRONG: "A tummy tuck removes excess skin... Would you like to book a consultation with our surgeon to discuss the details?"
- User: "Where is your clinic?" →  WRONG: "We're located at... Would you like to schedule a visit?"
- User: "Tell me about Dr. Arjun" →  WRONG: "Dr. Arjun is... Would you like to book an appointment with him?"

EXAMPLES OF CORRECT RESPONSES:
- User: "What is a tummy tuck?" →  RIGHT: "A tummy tuck (abdominoplasty) removes excess skin and fat from the abdomen and tightens the muscles. We offer mini, full, and circumferential options."
- User: "Where is your clinic?" →  RIGHT: "We're at **B4/60, Safdarjung Enclave, New Delhi - 110029**."
- User: "How much does liposuction cost?" →  RIGHT: "Pricing depends on your specific needs and is determined after a consultation. I can help you book an appointment if you'd like!"
═══════════════════════════════════════════════════════════════

RESPONSE LENGTH RULES:
- Keep replies to 2-3 sentences MAX. Imagine you're texting someone — short and helpful.
- Answer factual questions directly using the CLINIC CONTEXT below. Do NOT explanation-dump.
- You can use **bold** for important words and bullet points for short lists (max 3 items), but keep the total reply SHORT.

Other rules:
- Never diagnose or prescribe.
- For emergencies: tell them to call 108 or +91-40-9999-0000.
- Do NOT start with "Of course!", "Certainly!", "Great question!" or your name.
- Answer directly like a real person would.

Use the CLINIC CONTEXT below to answer factual questions accurately:
{context}"""


def build_messages(history: List[Dict], user_message: str, context: str) -> list:
    """
    Build LangChain message list from chat history + current question.
    We prepend the system prompt to the first message in the list so that
    instructions are always present in the context window.
    """
    messages = []
    formatted_system = SYSTEM_PROMPT.format(context=context)

    if not history:
        # First turn — prepend system prompt into the first human message
        combined = f"{formatted_system}\n\nUser: {user_message}"
        messages.append(HumanMessage(content=combined))
    else:
        # Subsequent turns — add history then current message
        turns = history[-6:]
        for idx, turn in enumerate(turns):
            role = turn.get("role", "")
            content = turn.get("content", "")
            if idx == 0:
                # Prepend the system prompt to the first message in context
                if role == "user":
                    combined = f"{formatted_system}\n\nUser: {content}"
                    messages.append(HumanMessage(content=combined))
                else:
                    combined = f"{formatted_system}\n\nAssistant: {content}"
                    messages.append(AIMessage(content=combined))
            else:
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))
        messages.append(HumanMessage(content=user_message))

    return messages


def get_chat_response(user_message: str, history: List[Dict]) -> str:
    """
    Get a chat response from Gemini using RAG context.

    Args:
        user_message: The user's latest message
        history: List of {role: "user"|"assistant", content: str} dicts

    Returns:
        The assistant's reply string
    """
    if not user_message.strip():
        return "I didn't catch that. What can I help you with?"

    # Retrieve relevant clinic context via RAG
    logger.info(f" Chat request received: '{user_message[:80]}'")
    try:
        context = rag.query_rag(user_message, k=4)
        logger.info(f" RAG context retrieved ({len(context)} chars)")
    except Exception as e:
        logger.error(f"RAG query failed: {e}")
        context = "Handa Aesthetics and Plastics — multi-specialty clinic in Hyderabad."

    # Build messages and invoke LLM
    try:
        llm = get_llm()
        messages = build_messages(history, user_message, context)
        logger.info(" Calling Gemini API... (waiting for response)")
        response = llm.invoke(messages)
        reply = response.content.strip()
        logger.info(f" Chat reply generated ({len(reply)} chars)")
        return reply
    except Exception as e:
        logger.error(f"Gemini LLM error: {e}", exc_info=True)
        return "Sorry, I'm having trouble connecting right now. Please call us at +91-40-9999-0000."
