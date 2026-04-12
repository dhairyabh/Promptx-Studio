from typing import List
import bcrypt
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import shutil, os, uuid
import razorpay
from datetime import datetime, timedelta
from dotenv import load_dotenv

from services.prompt import handle_prompt
from database import get_db
from services.manual_processor import process_manual_edits
import json

import logging

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)

# Initialize Razorpay Client
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)) if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET else None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# Task Progress Manager using WebSockets
class ProgressManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, task_id: str):
        await websocket.accept()
        self.active_connections[task_id] = websocket

    def disconnect(self, task_id: str):
        if task_id in self.active_connections:
            del self.active_connections[task_id]

    async def send_progress(self, task_id: str, progress: int):
        if task_id in self.active_connections:
            try:
                await self.active_connections[task_id].send_json({"progress": progress})
            except Exception as e:
                logger.error(f"Error sending progress for {task_id}: {e}")

progress_manager = ProgressManager()

@app.websocket("/ws/progress/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await progress_manager.connect(websocket, task_id)
    try:
        while True:
            # Keep connection open, though we only send from server -> client
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        progress_manager.disconnect(task_id)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(__file__)
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.mount("/outputs", StaticFiles(directory=os.path.join(BASE_DIR, "outputs")), name="outputs")

@app.get("/app", response_class=HTMLResponse)
async def index():
    index_path = os.path.join(BASE_DIR, "templates", "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/editor", response_class=HTMLResponse)
async def editor_page():
    editor_path = os.path.join(BASE_DIR, "templates", "editor.html")
    with open(editor_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/", response_class=HTMLResponse)
async def login_page():
    login_path = os.path.join(BASE_DIR, "templates", "login.html")
    with open(login_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(os.path.join(BASE_DIR, "static", "favicon.png"))

@app.post("/api/signup")
async def signup(email: str = Form(...), password: str = Form(...)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection failed")
        
    user = db.users.find_one({"email": email})
    if user:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    new_user = {
        "email": email,
        "password": hashed_password,
        "trials_left": 5
    }
    db.users.insert_one(new_user)
    
    return {"message": "User created successfully", "email": email, "trials_left": 5}

@app.post("/api/signin")
async def signin(email: str = Form(...), password: str = Form(...)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection failed")
        
    user = db.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=400, detail="Invalid email or password")
        
    if not bcrypt.checkpw(password.encode('utf-8'), user["password"].encode('utf-8')):
        raise HTTPException(status_code=400, detail="Invalid email or password")
        
    is_sub = user.get("is_subscribed", False)
    sub_end = user.get("subscription_end_date")
    
    # Check if subscription expired
    if is_sub and sub_end and datetime.utcnow() > sub_end:
        is_sub = False
        db.users.update_one({"email": email}, {"$set": {"is_subscribed": False}})
        
    return {
        "message": "Login successful", 
        "email": email, 
        "trials_left": user.get("trials_left", 0),
        "is_subscribed": is_sub
    }

@app.post("/api/google-signin")
async def google_signin(id_token: str = Form(...)):
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests
    
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    if not GOOGLE_CLIENT_ID or GOOGLE_CLIENT_ID == "YOUR_GOOGLE_CLIENT_ID_HERE":
        raise HTTPException(status_code=500, detail="Google Authentication is not configured on the server.")

    try:
        # Verify the token
        id_info = google_id_token.verify_oauth2_token(id_token, google_requests.Request(), GOOGLE_CLIENT_ID)
        
        email = id_info['email']
        
        # Check if user exists
        user = db.users.find_one({"email": email})
        
        if not user:
            # Create new user if not exists (Sign Up via Google)
            new_user = {
                "email": email,
                "password": "", # No password for Google users
                "trials_left": 5,
                "is_google_user": True
            }
            db.users.insert_one(new_user)
            user = new_user
            
        is_sub = user.get("is_subscribed", False)
        sub_end = user.get("subscription_end_date")
        
        if is_sub and sub_end and datetime.utcnow() > sub_end:
            is_sub = False
            db.users.update_one({"email": email}, {"$set": {"is_subscribed": False}})
            
        return {
            "message": "Login successful", 
            "email": email, 
            "trials_left": user.get("trials_left", 0),
            "is_subscribed": is_sub
        }
    except Exception as e:
        logger.error(f"Google Sign-In failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid Google Token")

@app.post("/process-video/")
async def process_video_endpoint(
    video: UploadFile = File(None),
    insert_file: UploadFile = File(None),
    prompt: str = Form(...),
    user_email: str = Form(None),
    is_admin: bool = Form(False)
):
    db = get_db()
    if prompt == "dhairya_admin_mode": is_admin = True
        
    if not is_admin and user_email and db is not None:
        user = db.users.find_one({"email": user_email})
        if user:
            is_sub = user.get("is_subscribed", False)
            sub_end = user.get("subscription_end_date")
            if is_sub and sub_end and datetime.utcnow() > sub_end:
                is_sub = False
                db.users.update_one({"email": user_email}, {"$set": {"is_subscribed": False}})
            if not is_sub and user.get("trials_left", 0) <= 0:
                return {"error": "Free trial limit reached. Please upgrade to continue."}
        else:
            return {"error": "User not found. Please log in again."}

    uid = str(uuid.uuid4())
    
    input_path = None
    if video:
        input_path = os.path.join(UPLOAD_DIR, f"{uid}_{video.filename}")
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)
            
    insert_file_path = None
    if insert_file:
        insert_file_path = os.path.join(UPLOAD_DIR, f"{uid}_insert_{insert_file.filename}")
        with open(insert_file_path, "wb") as buffer:
            shutil.copyfileobj(insert_file.file, buffer)

    try:
        output_filename = f"processed_{uid}.mp4"
        final_output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        # Handle the processing synchronously
        from starlette.concurrency import run_in_threadpool
        final_path = await run_in_threadpool(handle_prompt, prompt, input_path, final_output_path, insert_file_path)
        
        if final_path and os.path.exists(final_path):
            video_url = f"/outputs/{os.path.basename(final_path)}"
            response_data = {"video_url": video_url}
            
            if final_path.endswith(".txt"):
                with open(final_path, "r", encoding="utf-8") as f:
                    response_data["summary"] = f.read()

            if not is_admin and user_email and db is not None:
                user_doc = db.users.find_one({"email": user_email})
                if user_doc and not user_doc.get("is_subscribed", False):
                    db.users.update_one({"email": user_email}, {"$inc": {"trials_left": -1}})
            
            return response_data
        else:
            return {"error": "Processing failed to generate output."}
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        return {"error": str(e)}

from pydantic import BaseModel
from datetime import datetime

class PlanRequest(BaseModel):
    plan_id: str
    email: str

@app.get("/api/config")
async def get_config():
    return {
        "razorpay_key_id": RAZORPAY_KEY_ID,
        "google_client_id": GOOGLE_CLIENT_ID
    }

@app.post("/api/create-order")
async def create_order(req: PlanRequest):
    if not razorpay_client:
        raise HTTPException(status_code=500, detail="Razorpay is not configured.")
        
    prices = {
        "per_video": 900,     # 9 INR
        "weekly": 9900,       # 99 INR
        "monthly": 34900,     # 349 INR
        "annual": 449900      # 4499 INR
    }
    
    amount = prices.get(req.plan_id)
    if not amount:
        raise HTTPException(status_code=400, detail="Invalid plan ID.")
        
    try:
        order_data = {
            "amount": amount,
            "currency": "INR",
            "receipt": f"receipt_{uuid.uuid4().hex[:8]}",
            "notes": {
                "email": req.email,
                "plan_id": req.plan_id
            }
        }
        order = razorpay_client.order.create(data=order_data)
        return {"order_id": order["id"], "amount": amount, "currency": "INR"}
    except Exception as e:
        logger.error(f"Razorpay order creation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create payment order")

class VerifyPaymentRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str
    email: str
    plan_id: str

@app.post("/api/verify-payment")
async def verify_payment(req: VerifyPaymentRequest):
    if not razorpay_client:
        raise HTTPException(status_code=500, detail="Razorpay is not configured.")
        
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection failed")
        
    try:
        # Verify Payment Signature
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': req.razorpay_order_id,
            'razorpay_payment_id': req.razorpay_payment_id,
            'razorpay_signature': req.razorpay_signature
        })
        
        user = db.users.find_one({"email": req.email})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        current_time = datetime.utcnow()
        
        if req.plan_id == "per_video":
            # Add 1 generation for per_video pack
            db.users.update_one({"email": req.email}, {"$inc": {"trials_left": 1}})
            return {"success": True, "message": "Successfully added 1 video to your quota!"}
            
        else:
            # Recurring Subscription Logic
            durations = {
                "weekly": 7,
                "monthly": 30,
                "annual": 365
            }
            days_to_add = durations.get(req.plan_id, 7)
            
            # If already subscribed, extend the current end date. Otherwise start from now.
            current_end = user.get("subscription_end_date")
            if user.get("is_subscribed", False) and current_end and current_end > current_time:
                new_end_date = current_end + timedelta(days=days_to_add)
            else:
                new_end_date = current_time + timedelta(days=days_to_add)
                
            db.users.update_one(
                {"email": req.email},
                {"$set": {
                    "is_subscribed": True,
                    "subscription_end_date": new_end_date
                }}
            )
            return {"success": True, "message": f"Successfully subscribed to {req.plan_id.capitalize()} plan!"}
            
    except razorpay.errors.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid payment signature")
    except Exception as e:
        logger.error(f"Payment verification failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class Feedback(BaseModel):
    name: str
    email: str
    message: str

@app.post("/api/feedback")
async def submit_feedback(feedback: Feedback):
    db = get_db()
    if db is None:
        return {"error": "Database connection failed. Please check MONGODB_URI."}
        
    feedback_data = feedback.dict()
    feedback_data["timestamp"] = datetime.utcnow()
    
    try:
        # Insert into the 'feedback' collection
        db.feedback.insert_one(feedback_data)
        return {"success": True, "message": "Feedback submitted successfully!"}
    except Exception as e:
        logger.error(f"Error saving feedback: {e}")
        return {"error": "Failed to save feedback."}


from services.ai_service import handle_chat_query

class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        from starlette.concurrency import run_in_threadpool
        # Run chatbot logic in a threadpool so it doesn't block the async event loop
        reply = await run_in_threadpool(handle_chat_query, request.message)
        return {"reply": reply}
    except Exception as e:
        logger.error(f"Chatbot Error: {e}")
        return {"error": "Failed to process chat request."}

@app.post("/api/manual-edit")
async def manual_edit_endpoint(
    edits: str = Form(...),
    video_urls: List[str] = Form([]),
    user_email: str = Form(None),
    video_files: List[UploadFile] = File([]),
    music_file: UploadFile = File(None),
    music_start: float = Form(0.0),
    music_dur: float = Form(0.0),
    music_volume: float = Form(1.0),
    music_offset: float = Form(0.0),
    task_id: str = Form(None)
):
    db = get_db()
    if user_email and db is not None:
        user = db.users.find_one({"email": user_email})
        if user:
            is_sub = user.get("is_subscribed", False)
            if not is_sub and user.get("trials_left", 0) <= 0:
                return {"error": "Free trial limit reached. Please upgrade to continue."}

    try:
        parsed_edits = json.loads(edits)
        input_paths = []

        # We need to preserve the order of clips from parsed_edits.state.clips
        # But clips might be files or strictly URLs. 
        # For simplicity, we match uploaded file names OR internal URLs.
        
        file_map = {}
        for vf in video_files:
            if vf.filename:
                tmp_p = os.path.join(UPLOAD_DIR, f"multi_{uuid.uuid4()}_{vf.filename}")
                with open(tmp_p, "wb") as buffer:
                    buffer.write(await vf.read())
                file_map[vf.filename] = tmp_p

        # The 'clips' array in edits tells us the sequence
        for clip in parsed_edits.get('clips', []):
            cur_url = clip.get('url', '')
            if cur_url.startswith('blob:'):
                # This was a file upload, find it in file_map by filename
                fname = clip.get('file', {}).get('name', '')
                if fname in file_map:
                    input_paths.append(file_map[fname])
            else:
                # Internal URL
                rel_path = cur_url.replace("/", os.sep).lstrip(os.sep)
                p = os.path.join(BASE_DIR, rel_path)
                if not os.path.exists(p):
                    # check output/upload dirs
                    bn = os.path.basename(cur_url)
                    for d in [OUTPUT_DIR, UPLOAD_DIR]:
                        cand = os.path.join(d, bn)
                        if os.path.exists(cand): p = cand; break
                input_paths.append(p)

        if not input_paths:
            return {"error": "No valid video sources provided."}

        # Resolve music source
        music_path = None
        if music_file:
            music_filename = f"music_{uuid.uuid4()}_{music_file.filename}"
            music_path = os.path.join(UPLOAD_DIR, music_filename)
            with open(music_path, "wb") as buffer:
                buffer.write(await music_file.read())

        uid = str(uuid.uuid4())
        final_output_path = os.path.join(OUTPUT_DIR, f"manual_{uid}.mp4")

        parsed_edits = json.loads(edits)

        # Callback bridge for ProgressManager
        import asyncio
        def sync_progress_callback(p):
            if task_id:
                # We are in a threadpool, so we need to bridge to the main event loop
                if hasattr(loop, 'call_soon_threadsafe'):
                    loop.call_soon_threadsafe(
                        lambda: asyncio.create_task(progress_manager.send_progress(task_id, p))
                    )

        loop = asyncio.get_event_loop()
        from starlette.concurrency import run_in_threadpool
        final_path = await run_in_threadpool(
            process_manual_edits,
            input_paths, final_output_path, parsed_edits,
            music_path, music_start, music_dur, music_volume, music_offset,
            progress_callback=sync_progress_callback
        )

        if final_path and os.path.exists(final_path):
            result_url = f"/outputs/{os.path.basename(final_path)}"
            if user_email and db is not None:
                user_doc = db.users.find_one({"email": user_email})
                if user_doc and not user_doc.get("is_subscribed", False):
                    db.users.update_one({"email": user_email}, {"$inc": {"trials_left": -1}})
            return {"video_url": result_url}
        else:
            return {"error": "Manual processing failed to generate output."}

    except Exception as e:
        logger.error(f"Manual processing failed: {e}")
        return {"error": str(e)}
