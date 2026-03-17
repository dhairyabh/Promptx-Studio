import bcrypt
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import shutil, os, uuid
import razorpay
from datetime import datetime, timedelta
from dotenv import load_dotenv

from services.prompt import handle_prompt
from database import get_db

import logging

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)

# Initialize Razorpay Client
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)) if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET else None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

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

@app.post("/process-video/")
async def process_video_endpoint(
    video: UploadFile = File(None),
    insert_file: UploadFile = File(None), # The optional secondary audio or video
    prompt: str = Form(...),
    user_email: str = Form(None),
    is_admin: bool = Form(False)
):
    db = get_db()
    
    # Bypass logic if frontend declares admin mode
    # Double check dhairya_admin_unlimited just for safety
    if prompt == "dhairya_admin_mode":
        is_admin = True
        
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

    output_path = os.path.join(OUTPUT_DIR, f"processed_{uid}.mp4")

    from starlette.concurrency import run_in_threadpool
    try:
        # Assuming 'handle_prompt' is being renamed to 'process_user_instruction'
        # and 'video_path' in the instruction refers to 'input_path'
        final_path = await run_in_threadpool(handle_prompt, prompt, input_path, output_path, insert_file_path)
        logger.info(f"DEBUG: handle_prompt returned final_path='{final_path}'")
        
        video_url = f"/outputs/{os.path.basename(final_path)}"
        logger.info(f"Result ready: {final_path} -> {video_url}")

        response_data = {"video_url": video_url}
        
        # Decrement trials_left for normal users (only if not subscribed)
        if not is_admin and user_email and db is not None:
            user_doc = db.users.find_one({"email": user_email})
            if user_doc and not user_doc.get("is_subscribed", False):
                db.users.update_one({"email": user_email}, {"$inc": {"trials_left": -1}})

        # If the output is a text file (summary), read and return its content
        if final_path.endswith(".txt"):
            try:
                with open(final_path, "r", encoding="utf-8") as f:
                    response_data["summary"] = f.read()
            except Exception as e:
                logger.error(f"Error reading summary file: {e}")
                response_data["summary"] = "Error reading summary content."

        return response_data
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Processing Error: {error_msg}")
        return {
            "error": error_msg
        }

from pydantic import BaseModel
from datetime import datetime

class PlanRequest(BaseModel):
    plan_id: str
    email: str

@app.get("/api/config")
async def get_config():
    return {"razorpay_key_id": RAZORPAY_KEY_ID}

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
