from services.video import (
    remove_silence, add_captions, resize_to_vertical, resize_to_horizontal, 
    adjust_speed, trim_video, extract_audio, summarize_video, 
    generate_new_video, remove_noise, remove_watermark, insert_audio, insert_video,
    auto_zoom_speaker
)
import os
import shutil
import re
from functools import partial
import uuid
from services import ai_service
import logging

logger = logging.getLogger(__name__)

def handle_prompt(prompt_text: str, video_path: str = None, final_output_path: str = None, insert_file_path: str = None) -> str:
    """
    Analyzes the prompt and routes to the appropriate service.
    Now uses Gemini for robust natural language understanding of user instructions.
    """
    p = prompt_text.lower()
    logger.info(f"DEBUG: handle_prompt called. video_path={repr(video_path)}")
    
    # Normalize video_path
    if video_path is None or (isinstance(video_path, str) and video_path.strip() == "NONE"):
        video_path = None

    # Step 1: Use Gemini to extract intent and parameters (Handles misspellings/extra words)
    intent = ai_service.extract_intent_gemini(prompt_text)
    logger.info(f"DEBUG: AI Intent Extracted: {intent}")

    # Extract detected operation and parameters
    op = intent.get("operation") if intent else None
    params = intent.get("params", {}) if intent else {}

    # 1. Video Generation Operation (Text-to-Video)
    # Triggered if no video_path or if AI explicitly detects generation
    if not video_path or op == "generate_video":
        model_version = params.get("model", "veo-3.1-fast-generate-preview")
        if model_version == "veo": model_version = "veo-3.1-fast-generate-preview"
        
        # Extract duration from AI detected params
        duration = params.get("duration", 8)
        
        output_filename = f"generated_{uuid.uuid4()}.mp4"
        output_path = os.path.join("static", "outputs", output_filename)
        
        logger.info(f"DEBUG: Routing to Video Generation. Model: {model_version}, Duration: {duration}s")
        return ai_service.generate_video_veo(prompt_text, output_path, model=model_version, duration=duration)

    # 2. Video Editing Operations
    if not final_output_path:
        raise ValueError("final_output_path is required for editing operations.")

    # Summarization
    if op == "summarize" or any(k in p for k in ["summary", "summarize"]):
        base, _ = os.path.splitext(final_output_path)
        summary_path = base + ".txt"
        return summarize_video(video_path, summary_path, p)

    operations = []

    # Trim Logic (Prefer AI extracted values)
    start_trim = params.get("start_trim", 0)
    end_trim = params.get("end_trim", 0)
    
    # Manual fallback for trim if AI missed it but keywords exist
    if start_trim == 0 and end_trim == 0 and "trim" in p:
        s_match = re.search(r"start.*?(\d+)", p)
        if s_match: start_trim = int(s_match.group(1))
        e_match = re.search(r"end.*?(\d+)", p)
        if e_match: end_trim = int(e_match.group(1))

    if start_trim > 0 or end_trim > 0:
        operations.append(partial(trim_video, start_trim=start_trim, end_trim=end_trim))

    # Silence/Noise Removal
    if op == "remove_silence" or "silence" in p:
        operations.append(remove_silence)
    
    if op == "remove_noise" or any(k in p for k in ["noise", "clean audio"]):
        operations.append(remove_noise)

    # Visual Background Removal
    if op == "remove_background" or ("background" in p and any(k in p for k in ["remove", "isolate", "green", "change"])):
        operations.append(remove_background)

    # Watermark Removal
    if op == "remove_watermark" or "watermark" in p or "logo" in p:
        loc = params.get("watermark_location", "bottom_right")
        w_type = params.get("watermark_type", "small_logo")
        cw = params.get("watermark_width")
        ch = params.get("watermark_height")
        strat = params.get("watermark_strategy", "heal")
        operations.append(partial(remove_watermark, location=loc, watermark_type=w_type, custom_w=cw, custom_h=ch, strategy=strat))

    # Captions/Subtitles
    if op == "add_captions" or any(k in p for k in ["caption", "subtitle"]):
        target_lang = params.get("target_language")
        # Manual fallback for language
        if not target_lang:
            lang_match = re.search(r"\b(?:in|to)\s+([a-zA-Z]+)", p)
            if lang_match: target_lang = lang_match.group(1).lower()
        
        operations.append(partial(add_captions, target_language=target_lang))

    # Resizing / Zooming
    if op == "auto_zoom" or any(k in p for k in ["auto zoom", "auto-zoom", "track face", "follow face"]):
        operations.append(auto_zoom_speaker)
    elif op == "resize_vertical" or any(k in p for k in ["shorts", "reel", "vertical", "tiktok"]):
        operations.append(resize_to_vertical)
    elif op == "resize_horizontal" or any(k in p for k in ["horizontal", "landscape", "youtube"]):
        operations.append(resize_to_horizontal)

    # Speed Adjustment
    speed = params.get("speed", 1.0)
    if speed == 1.0:
        # Manual fallback
        speed_match = re.search(r"(\d+(\.\d+)?)x", p)
        if speed_match: speed = float(speed_match.group(1))
        elif "fast" in p: speed = 2.0
        elif "slow" in p: speed = 0.5
    
    if speed != 1.0:
        operations.append(partial(adjust_speed, speed=speed))

    # Determine Audio/Video Insertion first
    is_insert_audio = op == "insert_audio" or any(k in p for k in ["insert audio", "overlay audio", "meme", "sound effect", "insert the audio", "add audio"])
    
    # Catch phrases like "insert video", "insert the secondary video", "overlay video", "add video"
    # We check if (insert OR overlay OR add) AND video exists in the prompt
    is_insert_video = op == "insert_video" or (
        any(k in p for k in ["insert", "overlay", "add"]) and "video" in p
    )
    
    # Audio Extraction (skip if doing an insertion)
    if not (is_insert_audio or is_insert_video) and (op == "extract_audio" or any(k in p for k in ["audio", "mp3", "extract"])):
        operations.append(extract_audio)
        
    # Audio/Video Insertion
    if is_insert_audio or is_insert_video:
        if insert_file_path:
            insert_time = params.get("insert_timestamp", 0.0)
            
            # Manual fallback
            if insert_time == 0.0:
                time_match = re.search(r"at (\d+(\.\d+)?) sec", p)
                if time_match: 
                    insert_time = float(time_match.group(1))
                else:
                    time_match_2 = re.search(r"(\d+(\.\d+)?) second", p)
                    if time_match_2: insert_time = float(time_match_2.group(1))
            
            if is_insert_video:
                operations.append(partial(insert_video, insert_path=insert_file_path, timestamp_sec=insert_time))
            else:
                operations.append(partial(insert_audio, audio_path=insert_file_path, timestamp_sec=insert_time))
        else:
            logger.warning(f"DEBUG: Insertion requested but no insert_file_path provided. (is_insert_video={is_insert_video})")

    # Fallback: Just copy if no operations detected
    if not operations:
        shutil.copy(video_path, final_output_path)
        return final_output_path

    # Execute operations sequentially
    current_input = video_path
    for i, op_func in enumerate(operations):
        if i == len(operations) - 1:
            output = final_output_path
        else:
            base, ext = os.path.splitext(final_output_path)
            output = f"{base}_step{i}{ext}"
        
        current_input = op_func(current_input, output)

    return current_input
