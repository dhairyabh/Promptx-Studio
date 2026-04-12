import subprocess
import os
import re
import uuid
import shutil
from services.ai_service import generate_srt_gemini, generate_summary_gemini, generate_video_veo

def remove_silence(input_path, output_path, threshold="-30dB", min_silence_len=0.5):
    command_detect = [
        "ffmpeg", "-i", input_path,
        "-af", f"silencedetect=noise={threshold}:d={min_silence_len}",
        "-f", "null", "-"
    ]
    
    result = subprocess.run(command_detect, stderr=subprocess.PIPE, text=True)
    output = result.stderr
    
    silence_starts = [float(x) for x in re.findall(r"silence_start: ([\d\.]+)", output)]
    silence_ends = [float(x) for x in re.findall(r"silence_end: ([\d\.]+)", output)]
    
    if len(silence_starts) > len(silence_ends):
        dur_cmd = ["ffmpeg", "-i", input_path, "-hide_banner"]
        dur_res = subprocess.run(dur_cmd, stderr=subprocess.PIPE, text=True)
        dur_match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", dur_res.stderr)
        if dur_match:
            h, m, s = map(float, dur_match.groups())
            duration = h*3600 + m*60 + s
            silence_ends.append(duration)
        else:
            silence_starts = silence_starts[:len(silence_ends)]
            
    dur_cmd = ["ffmpeg", "-i", input_path, "-hide_banner"]
    dur_res = subprocess.run(dur_cmd, stderr=subprocess.PIPE, text=True)
    duration = 0
    dur_match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", dur_res.stderr)
    if dur_match:
        h, m, s = map(float, dur_match.groups())
        duration = h*3600 + m*60 + s
    
    clips = []
    current_pos = 0.0
    
    for start, end in zip(silence_starts, silence_ends):
        if start > current_pos:
            clips.append((current_pos, start))
        current_pos = end
        
    if current_pos < duration:
        clips.append((current_pos, duration))
        
    if not clips:
        import shutil
        shutil.copy(input_path, output_path)
        return output_path
        
    filter_complex = ""
    for i, (start, end) in enumerate(clips):
        filter_complex += f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}];"
        filter_complex += f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}];"
        
    for i in range(len(clips)):
        filter_complex += f"[v{i}][a{i}]"
    
    filter_complex += f"concat=n={len(clips)}:v=1:a=1[outv][outa]"
    
    command = [
        "ffmpeg", "-y", "-nostdin",
        "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        output_path
    ]
    
    subprocess.run(command, check=True)
    return output_path

def adjust_speed(input_path, output_path, speed=1.5):
    speed = max(0.5, min(speed, 2.0))
    
    command = [
        "ffmpeg", "-y", "-nostdin",
        "-i", input_path,
        "-filter_complex", f"[0:v]setpts=PTS/{speed}[v];[0:a]atempo={speed}[a]",
        "-map", "[v]", "-map", "[a]",
        output_path
    ]
    
    subprocess.run(command, check=True)
    return output_path

def insert_audio(input_path, output_path, audio_path, timestamp_sec=0.0):
    """
    Overlays a secondary audio file (like a meme sound) onto the main video
    at the exact specified timestamp_sec using FFmpeg.
    """
    if not audio_path or not os.path.exists(audio_path):
        import shutil
        print(f"DEBUG: Audio path {audio_path} not found. Returning original video.")
        shutil.copy(input_path, output_path)
        return output_path
        
    delay_ms = int(timestamp_sec * 1000)
    
    # FFmpeg complex filter:
    # 1. Take the secondary audio [1:a] and delay it by delay_ms
    # 2. Mix the primary audio [0:a] with the delayed secondary audio [aud1]
    # 'amix' is used so that both audios can be heard.
    # We use 'normalize=0' on modern FFmpeg, or let it auto-scale.
    # 'duration=first' ensures the output length matches the main video.
    
    # Check if input file has a video stream
    probe_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", input_path]
    has_video = False
    try:
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        if probe_result.stdout.strip() == "video":
            has_video = True
    except Exception as e:
        print(f"DEBUG: Error probing video: {e}")
        has_video = True # Assume video by default if probe fails

    command = [
        "ffmpeg", "-y", "-nostdin",
        "-i", input_path,
        "-i", audio_path,
        "-filter_complex", f"[1:a]adelay={delay_ms}|{delay_ms}[delayed_audio];[0:a][delayed_audio]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    ]
    
    if has_video:
        command.extend([
            "-map", "0:v",   # Keep original video
            "-map", "[aout]", # Use mixed audio
            "-c:v", "copy",  # Copy video codec for speed
            "-c:a", "aac",   # Re-encode mixed audio
        ])
    else:
        command.extend([
            "-map", "[aout]", # Use mixed audio only
            "-c:a", "libmp3lame", # Re-encode as mp3
            "-q:a", "2"
        ])
        
    command.append(output_path)
    
    subprocess.run(command, check=True)
    return output_path

def insert_video(input_path, output_path, insert_path, timestamp_sec=0.0):
    """
    Inserts a secondary video into the main video at the given timestamp_sec.
    Splits the main video at timestamp, inserts the secondary video (scaling it 
    first to match the main video's properties to prevent errors), and concatenates.
    """
    if not insert_path or not os.path.exists(insert_path):
        import shutil
        print(f"DEBUG: Video path {insert_path} not found. Returning original video.")
        shutil.copy(input_path, output_path)
        return output_path

    # FFmpeg complex concat approach:
    # We split input_path [0:v] into part A (before timestamp) and part B (after timestamp)
    # We take insert_path [1:v] and scale it to match [0:v] resolution/SAR to safely concat
    # Then we concat Part A + Scaled Inserted Video + Part B
    
    # Get main video properties to ensure safe scaling
    probe_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", 
                 "-show_entries", "stream=width,height,sample_aspect_ratio,r_frame_rate", 
                 "-of", "csv=p=0", input_path]
    probe_output = subprocess.run(probe_cmd, capture_output=True, text=True).stdout.strip().split(',')
    
    # Simple fallback if probe fails
    width_height_str = "1280:-2" # default safe fallback (e.g. 720p width)
    fps = "30"
    if len(probe_output) >= 4:
        w, h, sar, r_frame_rate = probe_output
        if w and w != "N/A":
            # Scale to match exact width, dynamic height preserving aspect
            width_height_str = f"{w}:-2" 
        # Attempt to grab fps for the concat framerate match
        if r_frame_rate and r_frame_rate != "N/A":
            fps = r_frame_rate

    # The filter_complex:
    # [0:v]trim=end={time}[v0]; [0:a]atrim=end={time}[a0]
    # [1:v]scale={scale_w_h},setsar=1,fps={fps}[v1]; [1:a]anull[a1]
    # [0:v]trim=start={time},setpts=PTS-STARTPTS[v2]; [0:a]atrim=start={time},asetpts=PTS-STARTPTS[a2]
    # [v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[outv][outa]
    filter_complex = (
        f"[0:v]trim=start=0:end={timestamp_sec},setpts=PTS-STARTPTS[v0]; "
        f"[0:a]atrim=start=0:end={timestamp_sec},asetpts=PTS-STARTPTS[a0]; "
        f"[1:v]scale={width_height_str},setsar=1,fps={fps}[v1]; "
        f"[1:a]anull[a1]; "
        f"[0:v]trim=start={timestamp_sec},setpts=PTS-STARTPTS[v2]; "
        f"[0:a]atrim=start={timestamp_sec},asetpts=PTS-STARTPTS[a2]; "
        f"[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[outv][outa]"
    )

    command = [
        "ffmpeg", "-y", "-nostdin",
        "-i", input_path,
        "-i", insert_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "[outa]",
        "-c:v", "libx264", 
        "-c:a", "aac",
        output_path
    ]
    
    try:
        subprocess.run(command, check=True)
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"DEBUG: FFmpeg Concat Failed: {e}")
        # Return fallback file if it crashed
        import shutil
        shutil.copy(input_path, output_path)
        return output_path

def trim_video(input_path, output_path, start_trim=0, end_trim=0):
    dur_cmd = ["ffmpeg", "-i", input_path, "-hide_banner"]
    dur_res = subprocess.run(dur_cmd, stderr=subprocess.PIPE, text=True)
    duration = 0
    dur_match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", dur_res.stderr)
    if dur_match:
        h, m, s = map(float, dur_match.groups())
        duration = h*3600 + m*60 + s

    start_time = start_trim
    
    new_duration = duration - start_trim - end_trim
    
    if new_duration <= 0:
        import shutil
        shutil.copy(input_path, output_path)
        return output_path
        
    command = [
        "ffmpeg", "-y", "-nostdin",
        "-ss", str(start_time),
        "-i", input_path,
        "-t", str(new_duration),
        "-c", "copy",
        output_path
    ]
    
    subprocess.run(command, check=True)
    return output_path

def _color_to_ffmpeg(color_str: str) -> str:
    """
    Converts standard color names or Hex (e.g., #FFFF00) to FFmpeg's &HBBGGRR format.
    """
    if not color_str:
        return "&HFFFFFF" # Default White
    
    color_map = {
        "yellow": "&H00FFFF",
        "red": "&H0000FF",
        "blue": "&HFF0000",
        "green": "&H00FF00",
        "black": "&H000000",
        "white": "&HFFFFFF",
        "purple": "&H800080",
        "orange": "&H00A5FF",
        "pink": "&HCB1DB1",
        "cyan": "&HFFFF00",
        "magenta": "&HFF00FF"
    }
    
    c = color_str.lower().strip()
    if c in color_map:
        return color_map[c]
    
    # Handle Hex (#RRGGBB)
    if c.startswith("#"):
        c = c[1:]
    if len(c) == 6:
        r = c[0:2]
        g = c[2:4]
        b = c[4:6]
        return f"&H{b}{g}{r}"
    
    return "&HFFFFFF"

def _get_google_font(font_name: str) -> str:
    """
    Attempts to download a Google Font (.ttf) if not present locally.
    Returns the font name to be used in FFmpeg style.
    """
    if not font_name or font_name.lower() == "arial":
        return "Arial Black"
    
    fonts_dir = os.path.join(os.getcwd(), "fonts")
    if not os.path.exists(fonts_dir):
        os.makedirs(fonts_dir, exist_ok=True)
        
    # Standardize name for file (e.g., "Arial Black" -> "ArialBlack")
    safe_name = "".join(x for x in font_name if x.isalnum())
    font_file = os.path.join(fonts_dir, f"{safe_name}.ttf")
    
    if os.path.exists(font_file):
        return font_name # Assume it works if file exists
        
    # Attempt to download from common Google Fonts GitHub patterns
    # Pattern 1: name / Name-Regular.ttf (most common)
    base_url = "https://github.com/google/fonts/raw/main/ofl"
    low_name = font_name.lower().replace(" ", "")
    cap_name = font_name.title().replace(" ", "")
    
    possible_urls = [
        f"{base_url}/{low_name}/{cap_name}-Regular.ttf",
        f"{base_url}/{low_name}/{font_name.replace(' ', '')}-Regular.ttf",
        f"{base_url}/{low_name}/{cap_name}.ttf",
        f"https://github.com/google/fonts/raw/main/apache/{low_name}/{cap_name}-Regular.ttf"
    ]
    
    import subprocess
    for url in possible_urls:
        print(f"Attempting to download font: {url}")
        try:
            res = subprocess.run(["curl", "-L", "-s", "-f", url, "-o", font_file], check=False)
            if res.returncode == 0 and os.path.getsize(font_file) > 1000:
                print(f"Successfully downloaded font: {font_name}")
                return font_name
        except:
            continue
            
    # Clean up if failed
    if os.path.exists(font_file):
        os.remove(font_file)
        
    return "Arial Black" # Fallback

def add_captions(input_path, output_path, target_language=None, font_name=None, font_color=None, has_bg=False):
    """
    Leverages Gemini API for high-speed transcription and translation with dynamic styling and font-loading.
    """
    srt_content = generate_srt_gemini(input_path, target_language)
    
    if srt_content.startswith("Error"):
        raise Exception(f"Caption Generation Failed: {srt_content}")

    # Use a fixed, space-free filename for the temporary SRT
    temp_srt_filename = f"temp_captions_{uuid.uuid4().hex[:8]}.srt"
    # Place SRT in current working directory (project root) to avoid path escaping issues
    temp_srt_path = temp_srt_filename
    
    with open(temp_srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)
    
    # Dynamic Styling & Font Loading
    downloaded_name = _get_google_font(font_name)
    fname = downloaded_name
    fcolor = _color_to_ffmpeg(font_color)
    
    # BorderStyle: 1 = Outline, 3 = Opaque Box
    b_style = 3 if has_bg else 1
    outline_val = 1 if not has_bg else 0
    
    style = (
        f"FontName={fname},"
        "FontSize=22,"
        f"PrimaryColour={fcolor},"
        "OutlineColour=&H000000,"
        "BackColour=&H80000000,"
        f"BorderStyle={b_style}," 
        f"Outline={outline_val},"
        "Shadow=0,"
        "Alignment=2,"
        "MarginV=30"
    )
    
    # Use absolute paths for -i and output
    abs_input_path = os.path.abspath(input_path)
    abs_output_path = os.path.abspath(output_path)
    
    # Transform path for FFmpeg subtitles filter on Windows
    abs_srt_path = os.path.abspath(temp_srt_path).replace("\\", "/").replace(":", "\\:")
    abs_fonts_dir = os.path.abspath("fonts").replace("\\", "/").replace(":", "\\:")
    
    command = [
        "ffmpeg", "-y", "-nostdin",
        "-i", abs_input_path,
        "-vf", f"subtitles='{abs_srt_path}':fontsdir='{abs_fonts_dir}':force_style='{style}'",
        "-c:a", "copy",
        abs_output_path
    ]
    
    # Run FFmpeg from the current directory where the SRT file is located
    subprocess.run(command, check=True)
    
    # Clean up temporary SRT file
    try:
        if os.path.exists(temp_srt_path):
            os.remove(temp_srt_path)
    except Exception as e:
        print(f"Warning: Could not remove temp srt: {e}")
    
    return output_path

def get_speech_intervals_local(input_path):
    """
    Uses FFmpeg silencedetect to find speech intervals.
    A professional local fallback when AI is unavailable.
    """
    import subprocess
    import re

    # detect silence
    command = [
        "ffmpeg", "-i", input_path,
        "-af", "silencedetect=noise=-35dB:d=0.2",
        "-f", "null", "-"
    ]
    
    # Run synchronously to capture stderr where silencedetect outputs its data
    result = subprocess.run(command, capture_output=True, text=True, stderr=subprocess.STDOUT)
    output = result.stdout

    silence_starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", output)]
    silence_ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", output)]
    
    # Get total duration
    duration_match = re.search(r"Duration: (\d{2}:\d{2}:\d{2}.\d{2})", output)
    total_duration = 0.0
    if duration_match:
        h, m, s = duration_match.group(1).split(':')
        total_duration = int(h)*3600 + int(m)*60 + float(s)

    if not silence_starts:
        return [(0, total_duration)] if total_duration > 0 else []

    speech_intervals = []
    current_time = 0.0
    
    # Ensure silence_ends matches silence_starts length if loop is mid-parse
    num_pairs = min(len(silence_starts), len(silence_ends))
    
    for i in range(num_pairs):
        start = silence_starts[i]
        end = silence_ends[i]
        if start > current_time:
            speech_intervals.append((current_time, start))
        current_time = end
        
    if current_time < total_duration:
        speech_intervals.append((current_time, total_duration))
        
    return speech_intervals

def remove_noise(input_path, output_path):
    """
    Nuclear-Grade Speech Enhancement (MAX Aggressive):
    1. Stage 1: Plosive/Rumble Kill (Highpass 100Hz).
    2. Stage 2: Heavy Spectral Scrubbing (40dB Reduction).
    3. Stage 3: Non-linear Means Smoothing (Aggressive).
    4. Stage 4: Surgical Audio Gate (Aggressive Threshold).
    5. Stage 5: Speech Normalization (Consistent Levels).
    6. Stage 6: The Absolute Void Gate (AI-driven).
    """
    print(f"Deploying NUCLEAR-GRADE accuracy engine for {os.path.basename(input_path)}...")
    srt_content = generate_srt_gemini(input_path)
    
    # Nuclear Filter Chain for extreme noise environments
    # afftdn: nr=40 (very aggressive), nf=-20 (handles louder noise floor)
    # anlmdn: s=7 (strong smoothing)
    # agate: threshold=-28dB (standard gate)
    # speechnorm: ensures voice is prominent
    base_vocal_chain = (
        "highpass=f=100,"
        "afftdn=nr=40:nf=-25," 
        "anlmdn=s=7,"
        "agate=threshold=-30dB:ratio=20:attack=2:release=100,"
        "speechnorm=e=10:r=0.0001,"
        "lowpass=f=10000"
    )

    if srt_content.startswith("Error"):
        print("AI Gating Unavailable. Switching to Local-Mastery Silence Detection...")
        intervals = get_speech_intervals_local(input_path)
    else:
        import re
        timestamp_pattern = re.compile(r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})")
        intervals = []
        
        def to_sec(s):
            h, m, sm = s.split(":")
            sec, ms = sm.split(",")
            return int(h)*3600 + int(m)*60 + int(sec) + int(ms)/1000.0

        for line in srt_content.splitlines():
            match = timestamp_pattern.search(line)
            if match:
                start_str, end_str = match.groups()
                intervals.append((to_sec(start_str), to_sec(end_str)))
        
        if not intervals:
            af_filters = base_vocal_chain
        else:
            # Stage 6: The Void Gate
            conditions = "+".join([f"between(t,{s:.3f},{e:.3f})" for s, e in intervals])
            af_filters = f"{base_vocal_chain},volume='if({conditions},1,0)':eval=frame"

    print(f"DEBUG: Final Audio Filter String: '{af_filters}'")

    command = [
        "ffmpeg", "-y", "-nostdin",
        "-i", input_path,
        "-af", af_filters,
        "-vcodec", "copy",
        output_path
    ]
    
    subprocess.run(command, check=True)
    return output_path

def remove_background(input_path, output_path):
    """
    Pro-Grade Background Removal:
    1. Uses Rembg (U2Net/ONNX) for surgical subject isolation.
    2. Replaces background with pure solid chroma green (#00FF00).
    3. Merges audio back for a professional final clip.
    """
    from rembg import remove, new_session
    import cv2
    import numpy as np
    from PIL import Image

    # Initialize a persistent session for much faster frame processing
    print("Initializing AI Segmentation Engine (this may take a moment)...")
    session = new_session()

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise Exception("Error: Could not open video file.")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    # Temporary path for video reconstruction
    temp_silent_path = os.path.join(os.path.dirname(output_path), f"temp_rembg_{os.path.basename(output_path)}")
    
    # Use cv2 + libx264 for high-quality intermediate
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_silent_path, fourcc, fps, (width, height))

    print(f"Executing Pro-Grade AI Isolation for {os.path.basename(input_path)}...")
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Convert BGR (cv2) to RGB (PIL/Rembg)
        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img)
        
        # Apply Rembg with solid green background
        # bgcolor is RGBA: (red, green, blue, alpha)
        # We want pure green: (0, 255, 0, 255)
        isolated_pil = remove(pil_img, bgcolor=(0, 255, 0, 255), session=session)
        
        # Convert back to BGR for VideoWriter
        output_frame = cv2.cvtColor(np.array(isolated_pil), cv2.COLOR_RGBA2BGR)
        out.write(output_frame)

    cap.release()
    out.release()

    # Final FFmpeg pass: Restore audio and fix orientation/encoding
    try:
        command_merge = [
            "ffmpeg", "-y", "-nostdin",
            "-i", temp_silent_path,
            "-i", input_path,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-map", "0:v:0",
            "-map", "1:a:0?",
            "-shortest",
            output_path
        ]
        subprocess.run(command_merge, check=True)
    except Exception as e:
        print(f"Merge Error: {e}")
        os.replace(temp_silent_path, output_path)
    finally:
        if os.path.exists(temp_silent_path):
            os.remove(temp_silent_path)

    return output_path

def resize_to_vertical(input_path, output_path):
    command = [
        "ffmpeg", "-y", "-nostdin",
        "-i", input_path,
        "-vf", "crop=ih*(9/16):ih",
        "-c:a", "copy",
        output_path
    ]
    
    subprocess.run(command, check=True)
    return output_path

def resize_to_horizontal(input_path, output_path):
    command = [
        "ffmpeg", "-y", "-nostdin",
        "-i", input_path,
        "-vf", "crop=iw:iw*(9/16)",
        "-c:a", "copy",
        output_path
    ]
    
    subprocess.run(command, check=True)
    return output_path

def change_resolution(input_path, output_path, resolution="1080p"):
    """
    Changes the video resolution (upscale/downscale) using FFmpeg.
    Supported inputs: '4k', '2k', '1080p', '720p', '480p', '360p'
    """
    res_map = {
        "4k": "3840:2160",
        "2k": "2048:1080",
        "1080p": "1920:1080",
        "720p": "1280:720",
        "480p": "854:480",
        "360p": "640:360"
    }
    
    # Handle pure numbers if given
    scale_str = res_map.get(resolution.lower())
    if not scale_str:
        if ":" in resolution:
            scale_str = resolution
        elif resolution.isdigit():
            # Assume it's height
            scale_str = f"-2:{resolution}"
        else:
            # Fallback to 1080p
            scale_str = "1920:1080"

    command = [
        "ffmpeg", "-y", "-nostdin",
        "-i", input_path,
        "-vf", f"scale={scale_str}",
        "-c:a", "copy",
        output_path
    ]
    
    subprocess.run(command, check=True)
    return output_path

def auto_zoom_speaker(input_path, output_path):
    """
    Auto-zooms and tracks the speaker's face to create a dynamic vertical (9:16) video.
    Uses OpenCV Haar Cascades for fast face detection and FFmpeg for cropping.
    """
    import cv2
    import numpy as np
    
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise Exception("Error: Could not open video file for auto-zoom.")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # Target 9:16 aspect ratio (we'll keep full height, crop width)
    target_h = height
    target_w = int(height * (9 / 16))
    
    if target_w > width:
        # Prevent stretching if original is narrower than 9:16
        target_w = width
        target_h = int(width * (16 / 9))

    # Fast face detector
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    centers = []
    
    print(f"DEBUG: Scanning {total_frames} frames for Auto-Zoom...")
    
    # Pass 1: Scan every Nth frame to find the face center trajectory
    step = max(1, int(fps / 4)) # Scan 4 frames per second
    
    # Default center if no face found
    default_cx = width // 2
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
        
        current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
        if current_frame % step != 0:
            continue
            
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Optimize for speed with scaleFactor and minNeighbors
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5, minSize=(60, 60))
        
        if len(faces) > 0:
            # Pick largest face
            faces = sorted(faces, key=lambda x: x[2]*x[3], reverse=True)
            x, y, w_f, h_f = faces[0]
            cx = x + w_f // 2
            centers.append((current_frame, cx))
        else:
            centers.append((current_frame, -1)) # -1 indicates no face

    cap.release()

    if not centers:
        print("DEBUG: No frames processed for auto-zoom. Falling back to static vertical resize.")
        return resize_to_vertical(input_path, output_path)

    # Post-process centers to smooth movement and handle missing detections
    processed_centers = []
    last_valid_cx = default_cx

    for frame_idx, cx in centers:
        if cx != -1:
            last_valid_cx = cx
        processed_centers.append(last_valid_cx)

    # Very basic smoothing (moving average)
    smoothed_cx = np.convolve(processed_centers, np.ones(5)/5, mode='same')
    
    # Convert back to a list of (frame, cx)
    final_trajectory = [(centers[i][0], int(smoothed_cx[i])) for i in range(len(centers))]

    # Build FFmpeg sendcmd file for dynamic cropping
    # This tells FFmpeg to move the crop box over time
    cmd_file_path = os.path.join(os.path.dirname(output_path), f"zoom_cmds_{uuid.uuid4().hex[:8]}.txt")
    
    with open(cmd_file_path, "w") as f:
        # Initialize crop filter
        # It's better to use variables in FFmpeg crop filter that we update
        f.write("# FFmpeg SendCmds for Auto-Zoom\n")
        
        for i in range(len(final_trajectory)):
            frame_n, cx = final_trajectory[i]
            
            # Calculate top-left x of the crop box
            # Ensure it doesn't go out of bounds
            crop_x = cx - (target_w // 2)
            crop_x = max(0, min(crop_x, width - target_w))
            
            # Time in seconds
            t_start = frame_n / fps
            
            if i < len(final_trajectory) - 1:
                t_end = final_trajectory[i+1][0] / fps
            else:
                t_end = total_frames / fps
                
            # Send command to update 'x' variable of crop filter
            # syntax: [start_time] [end_time] [target] [command] [argument]
            f.write(f"{t_start:.3f} {t_end:.3f} [enter] crop x {crop_x};\n")

    # Command to run FFmpeg with sendcmd and crop filter
    # Note: sendcmd requires precise filter graph setup
    
    # Windows paths need careful escaping for FFmpeg filters
    abs_cmd_path = os.path.abspath(cmd_file_path).replace("\\", "/")
    abs_cmd_path = abs_cmd_path.replace(":", "\\:")
    
    # The crop filter needs naming so sendcmd can target it.
    # e.g., sendcmd=f='commands.txt',crop=w=target_w:h=target_h:x='cx':y=0
    
    command = [
        "ffmpeg", "-y", "-nostdin",
        "-i", input_path,
        "-filter_complex", 
        f"sendcmd=f='{abs_cmd_path}',crop=w={target_w}:h={target_h}:y=0:x=0",
        "-c:v", "libx264",
        "-c:a", "copy",
        output_path
    ]
    
    try:
        subprocess.run(command, check=True)
    except Exception as e:
        print(f"DEBUG: FFmpeg Auto-Zoom Failed: {e}. Falling back to static crop.")
        resize_to_vertical(input_path, output_path)
    finally:
        if os.path.exists(cmd_file_path):
            os.remove(cmd_file_path)

    return output_path

def extract_audio(input_path, output_path):
    base, _ = os.path.splitext(output_path)
    audio_output = base + ".mp3"
    
    command = [
        "ffmpeg", "-y", "-nostdin",
        "-i", input_path,
        "-vn", 
        "-acodec", "libmp3lame",
        "-q:a", "2", 
        audio_output
    ]
    
    subprocess.run(command, check=True)
    return audio_output

def summarize_video(input_path, output_path, user_prompt: str = ""):
    """
    Performs deep AI analysis using Gemini.
    """
    if not output_path.endswith(".txt"):
        base, _ = os.path.splitext(output_path)
        output_path = base + ".txt"

    ai_summary = generate_summary_gemini(input_path, user_prompt)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ai_summary)

    return output_path

def generate_new_video(output_path, prompt, model: str = 'veo-3.1-fast-generate-preview'):
    """
    Generates a brand new video using Veo.
    """
    return generate_video_veo(prompt, output_path, model=model)

def remove_watermark(input_path, output_path, location="bottom_right", watermark_type="small_logo", custom_w=None, custom_h=None, strategy="heal"):
    """
    Advanced Watermark Removal:
    - "heal": Uses AI inpainting (OpenCV) with feathered edges.
    - "crop": Professional zero-blur edge removal (Best for corners).
    - "fast": Lightning-fast FFmpeg delogo.
    """
    if location is None:
        location = "bottom_right"
        
    import cv2
    import numpy as np
    import os
    import subprocess
    import uuid

    # 1. Get exact video dimensions
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise Exception("Error: Could not open video file.")
    
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    # Orientation check
    is_vertical = h > w

    if strategy == "fast":
        print(f"DEBUG: Using Lightning-Fast Strategy for {location}...")
        # Resolve dimensions for FFmpeg
        if custom_w and custom_w > 0:
            logo_w = int(w * (custom_w / 100))
        elif "full_width" in location:
            logo_w = w
        elif "banner" in watermark_type:
            logo_w = int(w * 0.50)
        else:
            logo_w = int(w * 0.25) if is_vertical else int(w * 0.15)

        if custom_h and custom_h > 0:
            logo_h = int(h * (custom_h / 100))
        elif "banner" in watermark_type or "full_width" in location:
            logo_h = int(h * 0.12)
        else:
            logo_h = int(h * 0.10) if is_vertical else int(h * 0.08)

        x, y = 0, 0
        if "top" in location: y = 0
        elif "bottom" in location: y = h - logo_h
        elif "middle" in location or "center" in location or "full_width" in location:
            y = (h // 2) - (logo_h // 2)

        if "left" in location: x = 0
        elif "right" in location: x = w - logo_w
        elif "center" in location: x = (w // 2) - (logo_w // 2)
        elif "full_width" in location: x = 0

        # Safety Clamping for FFmpeg
        x = max(1, min(x, w - logo_w - 1))
        y = max(1, min(y, h - logo_h - 1))
        logo_w = max(1, min(logo_w, w - x - 1))
        logo_h = max(1, min(logo_h, h - y - 1))

        command = [
            "ffmpeg", "-y", "-nostdin",
            "-i", os.path.abspath(input_path),
            "-vf", f"delogo=x={x}:y={y}:w={logo_w}:h={logo_h}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "copy",
            os.path.abspath(output_path)
        ]
        subprocess.run(command, check=True)
        return output_path

    if strategy == "crop" and not any(k in location for k in ["center", "middle", "full_width"]):
        print(f"DEBUG: Using Pro-Crop Strategy for zero-blur removal at {location}...")
        # Crop logic: Remove 8-10% of the edge where the logo sits
        crop_w, crop_h = w, h
        x_offset, y_offset = 0, 0
        
        # Standard mobile watermark margin is about 8-10%
        margin_w = int(w * 0.12) # Increased for transparency
        margin_h = int(h * 0.10)

        # For corners, we just shift the window
        if "bottom" in location:
            crop_h = h - margin_h
            y_offset = 0
        elif "top" in location:
            crop_h = h - margin_h
            y_offset = margin_h
            
        if "right" in location:
            crop_w = w - margin_w
            x_offset = 0
        elif "left" in location:
            crop_w = w - margin_w
            x_offset = margin_w

        # FFmpeg crop + scale
        # crop=w:h:x:y
        command = [
            "ffmpeg", "-y", "-nostdin",
            "-i", os.path.abspath(input_path),
            "-vf", f"crop={crop_w}:{crop_h}:{x_offset}:{y_offset},scale={w}:{h}:flags=bicubic",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            os.path.abspath(output_path)
        ]
        subprocess.run(command, check=True)
        return output_path

    # If we are here, we use HEAL (Standard for middle/banners)
    print(f"DEBUG: Using AI Healing for {location} (Full-Width/Center detected)...")
    
    # 2. HEAL Strategy (with upgraded feathered edges)
    # Determine Dimensions
    if custom_w and custom_w > 0:
        logo_w = int(w * (custom_w / 100))
    elif "full_width" in location:
        logo_w = w
    elif "banner" in watermark_type:
        logo_w = int(w * 0.50)
    elif is_vertical:
        logo_w = int(w * 0.25)
    else:
        logo_w = int(w * 0.15)

    if custom_h and custom_h > 0:
        logo_h = int(h * (custom_h / 100))
    else:
        logo_h = int(h * 0.08)
    
    x, y = 0, 0
    if "top" in location: y = 0
    if "bottom" in location: y = h - logo_h
    if "left" in location: x = 0
    if "right" in location: x = w - logo_w
    if "center" in location:
        x, y = (w // 2) - (logo_w // 2), (h // 2) - (logo_h // 2)

    # Safety Clamping
    x = max(0, min(x, w - logo_w))
    y = max(0, min(y, h - logo_h))
    logo_w = min(logo_w, w - x)
    logo_h = min(logo_h, h - y)

    temp_processed_path = os.path.join(os.path.dirname(output_path), f"temp_heal_{uuid.uuid4().hex[:8]}.mp4")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_processed_path, fourcc, fps, (w, h))

    # Create feathered mask
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[y:y+logo_h, x:x+logo_w] = 255
    # Feather the mask slightly to prevent hard edges
    mask_blur = cv2.GaussianBlur(mask, (21, 21), 0)

    print(f"Executing AI HEAL (Feathered) for {int(cap.get(cv2.CAP_PROP_FRAME_COUNT))} frames...")
    
    frame_count = 0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # Pre-calculate common alpha values
    alpha = mask_blur.astype(float) / 255.0
    alpha = cv2.merge([alpha, alpha, alpha])
    inv_alpha = 1.0 - alpha

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break

        if frame_count % 30 == 0:
            print(f"DEBUG: Healing Progress: {frame_count}/{total_frames} frames ({(frame_count/total_frames)*100:.1f}%)")

        # Healing
        healed = cv2.inpaint(frame, mask, 3, cv2.INPAINT_TELEA)
        
        # Alpha blend (Optimized with pre-calc)
        final_frame = (healed.astype(float) * alpha) + (frame.astype(float) * inv_alpha)
        out.write(final_frame.astype(np.uint8))
        frame_count += 1

    cap.release()
    out.release()

    # Final pass to restore audio
    try:
        command_merge = [
            "ffmpeg", "-y", "-nostdin",
            "-i", temp_processed_path,
            "-i", input_path,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-map", "0:v:0",
            "-map", "1:a:0?",
            "-shortest",
            output_path
        ]
        subprocess.run(command_merge, check=True)
    except Exception as e:
        print(f"Healing Merge Error: {e}")
        os.replace(temp_processed_path, output_path)
    finally:
        if os.path.exists(temp_processed_path):
            os.remove(temp_processed_path)

    return output_path

