"""
FastAPI Backend — MedCare Clinic AI Receptionist
Serves the frontend, manages VAPI assistant, and exposes RAG endpoints.
"""
import os
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import VAPI_PUBLIC_KEY, BASE_DIR
import rag
import vapi_service
import calendar_service
import chat_service


# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
# )
import os
import logging.handlers

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(
            "logs/chatbot.log",
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=7,
            encoding="utf-8", 
        )
    ]
)
logging.getLogger("watchfiles").setLevel(logging.WARNING)
logging.getLogger("watchfiles.main").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# ─── Global state ────────────────────────────────────────────────────────────
_assistant_id: str | None = None
_rag_ready: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: build RAG index and create/get VAPI assistant."""
    global _assistant_id, _rag_ready

    logger.info("=== MedCare Clinic Backend Starting ===")

    # Build RAG (runs in thread pool to avoid blocking event loop)
    logger.info("Initializing RAG knowledge base...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, rag.load_or_build_vector_store)
    _rag_ready = True
    logger.info("RAG knowledge base ready.")

    # Create or fetch VAPI assistant
    logger.info("Initializing VAPI assistant...")
    try:
        clinic_context = await loop.run_in_executor(None, rag.get_full_clinic_context)
        _assistant_id = await loop.run_in_executor(
            None, vapi_service.get_or_create_assistant, clinic_context
        )
        logger.info(f"VAPI Assistant ready: {_assistant_id}")
    except Exception as e:
        logger.error(f"VAPI assistant initialization failed: {e}")
        _assistant_id = None

    logger.info("=== Backend ready! ===")
    yield
    logger.info("=== Backend shutting down ===")


# ─── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="MedCare Clinic AI Receptionist",
    description="VAPI-powered clinic receptionist with LangChain RAG",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ─── Models ──────────────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str
    context: str


class ChatMessage(BaseModel):
    role: str        # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


# ─── Routes ──────────────────────────────────────────────────────────────────
@app.get("/", response_class=FileResponse)
async def serve_index():
    """Serve the main frontend page."""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(index_path)


@app.get("/api/assistant-id")
async def get_assistant_id():
    """Return VAPI assistant ID and public key for the frontend SDK."""
    if not _assistant_id:
        raise HTTPException(
            status_code=503,
            detail="VAPI assistant not yet initialized. Please wait and retry.",
        )
    return JSONResponse({
        "assistant_id": _assistant_id,
        "public_key": VAPI_PUBLIC_KEY,
        "status": "ready",
    })


@app.get("/api/status")
async def get_status():
    """Health check — returns initialization state."""
    return JSONResponse({
        "rag_ready": _rag_ready,
        "assistant_ready": _assistant_id is not None,
        "assistant_id": _assistant_id,
    })


@app.post("/api/query")
async def query_knowledge_base(request: QueryRequest):
    """Query the RAG knowledge base directly (for testing / admin use)."""
    if not _rag_ready:
        raise HTTPException(status_code=503, detail="RAG not yet initialized.")
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    loop = asyncio.get_event_loop()
    context = await loop.run_in_executor(None, rag.query_rag, request.question)
    return JSONResponse({"question": request.question, "context": context})


@app.post("/api/upload-docs")
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
):
    """
    Upload clinic documents (TXT files) to extend the RAG knowledge base.
    Processes in background and updates the VAPI assistant prompt.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    texts = []
    filenames = []

    for f in files:
        if not f.filename.endswith(".txt"):
            raise HTTPException(
                status_code=400,
                detail=f"Only .txt files are supported. Got: {f.filename}",
            )
        content = await f.read()
        texts.append(content.decode("utf-8", errors="replace"))
        filenames.append(f.filename)

    # Save files to disk
    os.makedirs(os.path.join(BASE_DIR, "data", "clinic_knowledge"), exist_ok=True)
    for fname, text in zip(filenames, texts):
        fpath = os.path.join(BASE_DIR, "data", "clinic_knowledge", fname)
        with open(fpath, "w", encoding="utf-8") as wf:
            wf.write(text)

    # Process in background
    async def process():
        global _assistant_id
        loop = asyncio.get_event_loop()
        count = await loop.run_in_executor(None, rag.add_documents_to_store, texts, filenames)
        logger.info(f"Added {count} chunks from {len(files)} uploaded files.")

        # Update VAPI assistant prompt
        if _assistant_id:
            new_context = await loop.run_in_executor(None, rag.get_full_clinic_context)
            updated = await loop.run_in_executor(
                None, vapi_service.update_assistant_prompt, _assistant_id, new_context
            )
            logger.info(f"VAPI assistant prompt updated: {updated}")

    background_tasks.add_task(process)

    return JSONResponse({
        "message": f"Processing {len(files)} file(s) in background.",
        "files": filenames,
    })


@app.get("/api/clinic-info")
async def get_clinic_info():
    """Return a summary of clinic knowledge for the UI display."""
    if not _rag_ready:
        return JSONResponse({"summary": "Loading clinic information..."})

    loop = asyncio.get_event_loop()
    summary = await loop.run_in_executor(
        None, rag.query_rag, "clinic name location hours contact services"
    )
    return JSONResponse({"summary": summary})


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Chat endpoint — uses Gemini + RAG to answer questions in a chat interface.
    Accepts conversation history for multi-turn context.
    """
    if not _rag_ready:
        return JSONResponse({"reply": "Still loading clinic knowledge. Please wait a moment and try again!"})

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    history = [{"role": m.role, "content": m.content} for m in request.history]

    loop = asyncio.get_event_loop()
    reply = await loop.run_in_executor(
        None, chat_service.get_chat_response, request.message, history
    )
    return JSONResponse({"reply": reply})


@app.post("/api/vapi-tool")
async def handle_vapi_tool_call(payload: dict):
    """
    Webhook endpoint for VAPI tool calling.
    VAPI sends a request here when the AI assistant decides to run a tool/function.
    """
    logger.info(f"Received VAPI tool call payload: {payload}")
    
    # VAPI payloads place toolCalls inside message block
    message = payload.get("message", {})
    tool_calls = message.get("toolCalls", [])
    
    results = []
    loop = asyncio.get_event_loop()
    
    for tool_call in tool_calls:
        tool_call_id = tool_call.get("id")
        func_info = tool_call.get("function", {})
        func_name = func_info.get("name")
        args = func_info.get("arguments", {})
        
        # Parse serialized JSON string if args is a string
        if isinstance(args, str):
            try:
                import json
                args = json.loads(args)
            except Exception as e:
                logger.error(f"Failed to parse arguments JSON string: {args}. Error: {e}")
                args = {}

        logger.info(f"Processing tool call {tool_call_id} for function {func_name} with arguments {args}")
        
        result_data = None
        try:
            if func_name == "check_available_slots":
                date_val = args.get("date")
                dept_val = args.get("department", "")
                
                # Fetch available slots from calendar service (offload to thread pool since it does network calls)
                slots = await loop.run_in_executor(
                    None, calendar_service.check_available_slots, date_val, dept_val
                )
                if slots:
                    result_data = f"Available slots for {dept_val} on {date_val}: {', '.join(slots)}"
                else:
                    result_data = f"There are no available slots for {dept_val} on {date_val}."
                    
            elif func_name == "book_appointment":
                patient_name = args.get("patient_name")
                phone_number = args.get("phone_number")
                department = args.get("department")
                doctor_name = args.get("doctor_name", "")
                date_val = args.get("date")
                time_val = args.get("time")
                
                # Perform booking via calendar service
                booking_result = await loop.run_in_executor(
                    None, 
                    calendar_service.book_appointment,
                    patient_name,
                    phone_number,
                    department,
                    doctor_name,
                    date_val,
                    time_val
                )
                
                if booking_result.get("status") == "success":
                    result_data = booking_result.get("message")
                else:
                    result_data = f"Failed to book appointment: {booking_result.get('message')}"
            else:
                result_data = f"Error: Unknown tool function '{func_name}'"
        except Exception as e:
            logger.error(f"Exception while executing tool {func_name}: {e}", exc_info=True)
            result_data = f"Error occurred during execution: {str(e)}"
            
        results.append({
            "toolCallId": tool_call_id,
            "result": result_data
        })
        
    response_payload = {"results": results}
    logger.info(f"Returning VAPI tool call response: {response_payload}")
    return JSONResponse(response_payload)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True,reload_excludes=["logs/*"],)

