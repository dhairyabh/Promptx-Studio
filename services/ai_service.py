from google import genai
import os
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
import fal_client

def get_api_key():
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    load_dotenv(dotenv_path=env_path, override=True)
    return os.environ.get("GEMINI_API_KEY")

def generate_summary(transcript: str):
    api_key = get_api_key()
    if not api_key:
        return "Error: Gemini API Key is missing. Please set it in services/ai_service.py."

    try:
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        Provide a detailed, descriptive paragraph summary of the following video transcript. 
        Focus on explaining the flow of information and the core message.
        Do not use headings, bullet points, or sections. Just a single comprehensive paragraph.

        TRANSCRIPT:
        {transcript}
        """

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        return f"Error analyzing video: {str(e)}"

def _upload_and_wait(client, media_path):
    print(f"Uploading {media_path} to Gemini...")
    uploaded_file = client.files.upload(file=media_path)
    
    import time
    while uploaded_file.state.name == "PROCESSING":
        print("Waiting for file to be processed by Gemini...")
        time.sleep(2)
        uploaded_file = client.files.get(name=uploaded_file.name)
        
    if uploaded_file.state.name == "FAILED":
        raise Exception("Gemini file processing failed.")
    return uploaded_file

def generate_srt_gemini(media_path: str, target_language: str = None):
    """
    Uploads a media file to Gemini and requests it to generate captions in SRT format.
    """
    api_key = get_api_key()
    if not api_key or api_key == "YOUR_GEMINI_API_KEY":
        return "Error: Gemini API Key is missing."

    import time
    max_retries = 5
    retry_delay = 2 # Initial delay in seconds

    for attempt in range(max_retries):
        try:
            client = genai.Client(api_key=api_key)
            uploaded_file = _upload_and_wait(client, media_path)

            lang_instruction = f"TRANSLATE EVERYTHING to {target_language}. Even if the original language is different, the output SRT MUST be in {target_language}." if target_language else "transcribe to the original language"
            prompt = f"""
            Generate a professional SRT subtitle file for this media with EXTRAORDINARY SURGICAL PRECISION.
            Instruction: {lang_instruction}.
            Rules:
            - Output ONLY the raw SRT text. No markdown tags, no notes.
            - STRICT Timestamp Format: HH:MM:SS,mmm (e.g., 00:00:05,123 --> 00:00:10,500).
            - WORD-BY-WORD PRECISION: Each SRT segment MUST contain a MAXIMUM of 1 to 3 words.
            - TIMESTAMPS MUST BE SURGICALLY TIGHT: Start the timestamp at the EXACT millisecond the first word begins, and end EXACTLY when the last word in that segment ends.
            - WORD-BY-WORD PRECISION: Each SRT segment MUST contain a MAXIMUM of 1 to 3 words.
            - COMPLETELY IGNORE the original language if a target language is specified; PRODUCING ONLY {target_language if target_language else 'ORIGINAL LANGUAGE'} SUBTITLES.
            """

            print(f"Generating SRT using Gemini 2.5 Flash (Target: {target_language if target_language else 'Original'}). Attempt {attempt + 1}/{max_retries}...")
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[uploaded_file, prompt]
            )
            
            try: client.files.delete(name=uploaded_file.name)
            except: pass
            
            raw_srt = response.text.strip()
            return _fix_srt_content(raw_srt)

        except Exception as e:
            error_msg = str(e)
            is_transient = "503" in error_msg or "429" in error_msg or "UNAVAILABLE" in error_msg or "RESOURCE_EXHAUSTED" in error_msg
            
            if is_transient and attempt < max_retries - 1:
                print(f"Transient error ({error_msg}) encountered. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= 2 # Exponential backoff
                continue
            
            if "429" in error_msg:
                print(f"Quota Error (429): Gemini API limit reached for Gemini 2.5 Flash.")
            
            return f"Error generating SRT: {error_msg}"

def _adjust_timestamp(ts_str: str, offset_sec: float) -> str:
    """
    Shifts a timestamp string (HH:MM:SS,mmm) by offset_sec.
    Ensures the time doesn't go below 00:00:00,000.
    """
    try:
        h, m, sm = ts_str.split(':')
        s, ms = sm.split(',')
        total_ms = (int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms))
        
        offset_ms = int(offset_sec * 1000)
        new_total_ms = max(0, total_ms + offset_ms)
        
        new_h = new_total_ms // 3600000
        new_m = (new_total_ms % 3600000) // 60000
        new_s = (new_total_ms % 60000) // 1000
        new_ms = new_total_ms % 1000
        
        return f"{new_h:02d}:{new_m:02d}:{new_s:02d},{new_ms:03d}"
    except:
        return ts_str

def _fix_srt_content(text, offset_sec: float = -0.3):
    """
    Attempts to fix common SRT formatting issues and applies a timing offset.
    Default offset is -0.3s to make captions feel more 'snappy' and aligned with speech onset.
    """
    import re
    
    # Pre-process: handle common LLM output quirks
    text = text.replace('```srt', '').replace('```', '').strip()
    
    raw_blocks = re.split(r'\n\s*\n', text)
    fixed_blocks = []
    index = 1
    
    for block in raw_blocks:
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if not lines:
            continue
            
        # Find timestamp line
        ts_line_idx = -1
        for i, line in enumerate(lines):
            if "-->" in line:
                ts_line_idx = i
                break
        
        if ts_line_idx == -1:
            continue # Not a valid block
            
        # 1. Ensure Index
        # If the first line is not a number, the index is missing.
        # Note: ts_line_idx might be 0 if index is missing.
        block_lines = [str(index)]
        
        # 2. Extract and Normalize Timestamps
        ts_line = lines[ts_line_idx]
        ts_parts = ts_line.split("-->")
        if len(ts_parts) != 2:
            continue
            
        def normalize_ts(ts):
            ts = ts.strip().replace('.', ',')
            # Handle MM:SS,mmm or SS,mmm
            colons = ts.count(':')
            if colons == 1:
                ts = "00:" + ts
            elif colons == 0:
                ts = "00:00:" + ts
            
            # Ensure 2 digits for H, M, S
            parts = ts.split(':')
            if len(parts) == 3:
                h = parts[0].zfill(2)
                m = parts[1].zfill(2)
                s_ms = parts[2]
                if ',' not in s_ms:
                     # If no comma, maybe it's SSmmm? Or just SS?
                     if len(s_ms) > 2:
                         s = s_ms[:2]
                         ms = s_ms[2:].ljust(3, '0')[:3]
                         s_ms = f"{s},{ms}"
                     else:
                         s_ms = s_ms.zfill(2) + ",000"
                else:
                    s, ms = s_ms.split(',')
                    s = s.zfill(2)
                    ms = ms.ljust(3, '0')[:3]
                    s_ms = f"{s},{ms}"
                return f"{h}:{m}:{s_ms}"
            return ts

        raw_start = normalize_ts(ts_parts[0])
        raw_end = normalize_ts(ts_parts[1])
        
        # Apply Offset
        start_ts = _adjust_timestamp(raw_start, offset_sec)
        end_ts = _adjust_timestamp(raw_end, offset_sec)
        
        block_lines.append(f"{start_ts} --> {end_ts}")
        
        # 3. Append Text
        block_lines.extend(lines[ts_line_idx+1:])
        
        fixed_blocks.append("\n".join(block_lines))
        index += 1
        
    return "\n\n".join(fixed_blocks) + "\n"



def generate_summary_gemini(media_path: str, user_prompt: str = ""):
    """
    Uploads a media file to Gemini and requests a deep content analysis summary,
    matching the language of the user's prompt.
    """
    api_key = get_api_key()
    if not api_key or api_key == "YOUR_GEMINI_API_KEY":
        return "Error: Gemini API Key is missing."

    import time
    max_retries = 3
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            client = genai.Client(api_key=api_key)
            uploaded_file = _upload_and_wait(client, media_path)

            prompt = f"""
            Analyze this video/audio and provide a comprehensive, descriptive paragraph summary.
            User Instruction: {user_prompt}
            
            CRITICAL:
            1. Detect the language used in the 'User Instruction' above.
            2. Generate the entire summary in that SAME language.
            3. Provide only the descriptive paragraph. Do not use headings, titles, or bullet points.
            """

            print(f"Analyzing video content with Gemini 2.5 Flash. Attempt {attempt + 1}/{max_retries}...")
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[uploaded_file, prompt]
            )
            
            try: client.files.delete(name=uploaded_file.name)
            except: pass
            
            return response.text.strip()
        except Exception as e:
            error_msg = str(e)
            is_transient = "503" in error_msg or "429" in error_msg or "UNAVAILABLE" in error_msg or "RESOURCE_EXHAUSTED" in error_msg

            if is_transient and attempt < max_retries - 1:
                print(f"Transient error ({error_msg}) encountered during analysis. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= 2
                continue

            return f"Error analyzing video: {error_msg}"

QUOTA_FILE = "quota_usage.json"
MAX_DAILY_QUOTA_SEC = 30 # Reduced to 30s to stay within most preview limits

def _get_quota_usage():
    if not os.path.exists(QUOTA_FILE):
        return {"date": str(datetime.now().date()), "seconds_used": 0}
    try:
        with open(QUOTA_FILE, "r") as f:
            data = json.load(f)
            if data.get("date") != str(datetime.now().date()):
                return {"date": str(datetime.now().date()), "seconds_used": 0}
            return data
    except:
        return {"date": str(datetime.now().date()), "seconds_used": 0}

def _update_quota_usage(seconds):
    usage = _get_quota_usage()
    usage["seconds_used"] += seconds
    with open(QUOTA_FILE, "w") as f:
        json.dump(usage, f)

def generate_video_veo(prompt: str, output_path: str, model: str = 'veo-3.1-fast-generate-preview', duration: int = 8):
    """
    Generates a video using Google Veo based on the provided prompt.
    Supports extended durations by looping generation.
    Includes Quota Management and Model Fallback (Fast).
    """
    api_key = get_api_key()
    if not api_key or api_key == "YOUR_GEMINI_API_KEY":
        return "Error: Gemini API Key is missing."

    # 1. Quota Check
    usage = _get_quota_usage()
    remaining = MAX_DAILY_QUOTA_SEC - usage["seconds_used"]
    target_duration = min(duration, remaining)
    
    if target_duration <= 0:
        raise Exception(f"Local Quota Exceeded: You have used {usage['seconds_used']}s of your {MAX_DAILY_QUOTA_SEC}s daily safety limit. Please wait until tomorrow or increase MAX_DAILY_QUOTA_SEC in ai_service.py.")

    try:
        client = genai.Client(api_key=api_key)
        
        current_duration = 0
        video = None
        
        print(f"Generating video with Veo ({model}): '{prompt}' (Target: {target_duration}s)")
        
        def call_veo(target_model, current_video=None):
            if current_video:
                return client.models.generate_videos(model=target_model, video=current_video, prompt=prompt)
            return client.models.generate_videos(model=target_model, prompt=prompt)

        # Try primary model first, fallback to fast if quota hit
        try:
            operation = call_veo(model)
        except Exception as e:
            if ("429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)) and "fast" not in model:
                print("Primary model quota hit. Attempting fallback to 'fast-generate' variant...")
                fallback_model = model.replace("generate-preview", "fast-generate-preview") if "preview" in model else "veo-3.1-fast-generate-preview"
                operation = call_veo(fallback_model)
            else:
                raise e

        import time
        while not operation.done:
            print(f"Generation in progress...")
            time.sleep(5)
            operation = client.operations.get(operation)

        if operation.error:
            error_msg = str(operation.error)
            if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
                 raise Exception("GOOGLE REMOTE QUOTA: Your GCP account has reached its Veo limit for now. These limits are very strict in preview (often 1-5 videos/day). Please wait 15-30 minutes or check your quota in the Google Cloud Console (https://console.cloud.google.com/benchmark/quotas).")
            raise Exception(f"Veo generation failed: {operation.error}")

        video = operation.result.generated_videos[0]
        current_duration = 8 # Initial gen
        
        # Extension Loop
        while current_duration < target_duration:
            if (usage["seconds_used"] + current_duration + 7) > MAX_DAILY_QUOTA_SEC:
                print("Stopping: Next extension would exceed daily quota.")
                break

            print(f"Extending video... (Current: {current_duration}s -> Target: {target_duration}s)")
            try:
                operation = call_veo(model, current_video=video)
            except Exception as e:
                 if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                     print("Quota hit during extension. Returning partial video.")
                     break
                 raise e

            while not operation.done:
                time.sleep(5)
                operation = client.operations.get(operation)
            
            if operation.error:
                print(f"Extension failed: {operation.error}. Returning partial video.")
                break 

            video = operation.result.generated_videos[0]
            current_duration += 7

        # Save
        video_bytes = client.files.download(file=video)
        with open(output_path, "wb") as f:
            f.write(video_bytes)
        
        _update_quota_usage(current_duration)
        return output_path
        
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            raise Exception("REMOTE QUOTA EXHAUSTED: Google has temporarily blocked new video generations for your API key. This is a limit on their side. Try again in 15 minutes, or use a shorter prompt.")
        raise Exception(f"Veo Error: {error_str}")

def generate_video_wan(prompt: str, output_path: str, duration: int = 5, script: str = None):
    """
    Generates video using Wan2.2 (via Fal.ai).
    If a script is provided, it generates TTS audio and performs lip-sync.
    """
    fal_key = os.getenv("FAL_KEY")
    if not fal_key:
        raise Exception("Error: FAL_KEY is missing in .env file. Please get it from fal.ai.")

    os.environ["FAL_KEY"] = fal_key

    try:
        print(f"Generating video with Wan2.2 (via Fal.ai): '{prompt}'")
        
        # 1. Generate the base video visuals
        handler = fal_client.submit(
            "fal-ai/wan/v2.2-a14b/text-to-video",
            arguments={
                "prompt": prompt,
                "aspect_ratio": "16:9",
                "resolution": "480p",
                "num_frames": 161 if duration > 5 else (121 if duration >= 5 else 81), 
                "frames_per_second": 24,
                "negative_prompt": "blurry, low quality, distorted, static, text, watermark, person indoors (unless specified), unrelated objects",
            },
        )
        
        result = handler.get()
        video_url = result.get("video", {}).get("url")
        
        if not video_url:
            raise Exception("Fal.ai returned no video URL.")

        # 2. Handle Speaking Character (TTS + Lip Sync)
        if script:
            try:
                print(f"Detected script: '{script}'. Generating TTS and Lip-Sync...")
                
                # a) Generate TTS Audio via MiniMax
                tts_handler = fal_client.submit(
                    "fal-ai/minimax-speech",
                    arguments={
                        "text": script,
                        "voice": "male_1" if "man" in prompt.lower() or "boy" in prompt.lower() else "female_1"
                    }
                )
                tts_result = tts_handler.get()
                audio_url = tts_result.get("audio", {}).get("url")
                
                if audio_url:
                    # b) Perform Lip Sync via Sync v2.0
                    print(f"Audio generated. Syncing lips to video...")
                    sync_handler = fal_client.submit(
                        "fal-ai/sync-lipsync/v2.0",
                        arguments={
                            "video_url": video_url,
                            "audio_url": audio_url
                        }
                    )
                    sync_result = sync_handler.get()
                    synced_video_url = sync_result.get("video", {}).get("url")
                    
                    if synced_video_url:
                        print("Lip-sync successful!")
                        video_url = synced_video_url
                    else:
                        print("Warning: Lip-sync failed to return a URL. Falling back to background sound.")
            except Exception as e:
                print(f"Warning: TTS/LipSync workflow failed: {e}. Falling back to default sound.")

        # 3. Add background sound properties if not lip-synced or as enhancement
        # Note: MMAudio usually adds SFX/Ambient, so we only run it if no script or as enhancement.
        # For now, let's skip MMAudio if lip-sync was successful to avoid audio overlap.
        if not script or (script and "synced_video_url" not in locals()):
            try:
                print(f"Generating synchronized background audio with MMAudio V2...")
                audio_handler = fal_client.submit(
                    "fal-ai/mmaudio-v2",
                    arguments={
                        "video_url": video_url,
                        "prompt": prompt,
                        "negative_prompt": "noisy, low quality, distorted audio, static",
                    }
                )
                audio_result = audio_handler.get()
                final_video_url = audio_result.get("video", {}).get("url")
                
                if final_video_url:
                    video_url = final_video_url
            except Exception as audio_err:
                print(f"Warning: MMAudio failed: {audio_err}")

        # Ensure directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Download the final video
        response = requests.get(video_url, stream=True)
        response.raise_for_status()
        
        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        return output_path
        
    except Exception as e:
        raise Exception(f"Wan2.2 Generation Error: {str(e)}")

def extract_intent_gemini(user_prompt: str):
    """
    Uses Gemini to extract structured intent from a natural language prompt.
    Returns a JSON-like dictionary with the detected operation and parameters.
    Includes exponential backoff for transient AI service errors (503, 429).
    """
    api_key = get_api_key()
    if not api_key or api_key == "YOUR_GEMINI_API_KEY":
        return None

    import time
    max_retries = 5
    retry_delay = 2 # Initial delay in seconds

    for attempt in range(max_retries):
        try:
            client = genai.Client(api_key=api_key)
            
            system_prompt = """
            You are an AI Video Editor intent extractor. Your job is to convert natural language instructions into structure JSON.
            
            Available Operations:
            - \"generate_video\": User wants to create a video from text (no input file).
            - \"summarize\": User wants a summary of the video.
            - \"trim\": User wants to cut time from start or end.
            - \"remove_silence\": User wants to remove silent parts.
            - \"remove_noise\": User wants to clean audio/remove background noise.
            - \"add_captions\": User wants to add subtitles.
            - \"insert_audio\": User wants to overlay/insert an uploaded audio file (e.g. meme sound) at a specific time in the video.
            - \"insert_video\": User wants to insert/splice an uploaded secondary video file into the main video at a specific time.
            - \"resize_vertical\": User wants 9:16 aspect ratio (Shorts/Reels).
            - \"resize_horizontal\": User wants 16:9 aspect ratio.
            - \"adjust_speed\": User wants to change video speed.
            - \"extract_audio\": User wants to save as MP3.
            - \"remove_background\": User wants to remove the visual background (green screen).
            - \"remove_watermark\": User wants to remove a logo or watermark from the video.
            - \"change_resolution\": User wants to change video resolution (e.g. 720p, 1080p, 4k).

            Parameters to extract:
            - \"start_trim\" (int): Seconds to remove from start. Default 0.
            - \"end_trim\" (int): Seconds to remove from end. Default 0.
            - \"duration\" (int): Requested duration for NEW video generation (in seconds). Default 8 if not specified.
            - \"insert_timestamp\" (float): The exact absolute time (in seconds) the user wants the secondary audio or video inserted at. (e.g., 'at 5 seconds' means 5.0). Default 0.0.
            - \"target_language\" (str): Language for captions/summary.
            - \"target_resolution\" (str): Target resolution (e.g., '720p', '1080p', '4k').
            - \"caption_font\" (str): Specific font name for captions (e.g., 'Arial', 'Impact', 'Verdana').
            - \"caption_color\" (str): Specific color for captions (e.g., 'Yellow', 'Red', '#FFFF00').
            - \"caption_has_bg\" (bool): Whether the user explicitly wants a background box for captions. Default false.
            - \"speed\" (float): Speed multiplier (e.g., 1.5, 0.5). Default 1.0.
            - \"model\" (str): The video model to use. Use 'wan' as the STRICT DEFAULT.
            - \"visual_prompt\" (str): A HIGHLY DETAILED, CINEMATIC, and DESCRIPTIVE visual-only prompt for video generation. 

            Output Format (JSON ONLY):
            {
                \"operation\": \"operation_name\",
                \"params\": {
                    \"start_trim\": 0,
                    \"end_trim\": 0,
                    \"duration\": 8,
                    \"insert_timestamp\": 0.0,
                    \"target_language\": null,
                    \"target_resolution\": null,
                    \"caption_font\": null,
                    \"caption_color\": null,
                    \"caption_has_bg\": false,
                    \"speed\": 1.0,
                    \"model\": \"wan\",
                    \"visual_prompt\": null
                }
            }
            
            If multiple operations are requested, pick the primary one or return a list if possible, but for now, focus on the most prominent one.
            If the user misspelled words (e.g., 'tirm', 'vidoe', 'captin'), detect the correct intent anyway.
            """

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"{system_prompt}\n\nUser Instruction: {user_prompt}",
                config={
                    'response_mime_type': 'application/json'
                }
            )
            
            import json
            return json.loads(response.text.strip())

        except Exception as e:
            error_msg = str(e)
            is_transient = "503" in error_msg or "429" in error_msg or "500" in error_msg or "UNAVAILABLE" in error_msg or "RESOURCE_EXHAUSTED" in error_msg
            
            if is_transient and attempt < max_retries - 1:
                print(f"DEBUG: Transient error during intent extraction ({error_msg}). Retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2 # Exponential backoff
                continue
                
            print(f"DEBUG: Intent extraction failed after {attempt+1} attempts: {error_msg}")
            return None

def handle_chat_query(user_message: str) -> str:
    """
    Handles user chat queries regarding the PROMPTX STUDIO platform.
    """
    api_key = get_api_key()
    if not api_key or api_key == "YOUR_GEMINI_API_KEY":
        return "I'm sorry, my AI backend is not configured correctly (Missing API Key)."

    try:
        client = genai.Client(api_key=api_key)
        
        system_prompt = """
        You are the friendly and helpful Customer Support AI for PROMPTX STUDIO.
        PROMPTX STUDIO is an AI-powered Video Editing Engine that lets users edit videos using simple text prompts.
        Features include: AI Silence Removal, AI Captions, AI Trim, AI Vertical/Horizontal Resizing, AI Resolution Changing (e.g. upscaling to 1080p), Video generation from text (Veo), and AI audio extraction.
        Keep your answers concise, friendly, and helpful. Do not use complex markdown formatting unless necessary.
        If a user asks how to do something, tell them they can just upload their video and type what they want in the prompt box!
        """

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"{system_prompt}\n\nUser: {user_message}",
        )
        
        return response.text.strip()
    except Exception as e:
        print(f"DEBUG: Chat handle failed: {e}")
        return f"I'm sorry, I'm having trouble connecting to my brain right now. Please try again later. ({str(e)})"
