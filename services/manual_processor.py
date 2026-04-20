import subprocess
import os
import json
import uuid
import logging
import math

logger = logging.getLogger(__name__)

def generate_ffmpeg_expr(keyframes, base_val=100, axis=None):
    """
    Generates a nested FFmpeg if() expression for linear interpolation between keyframes.
    """
    # Fix: Ensure keyframes is a list/dict before calling len()
    if not keyframes or not isinstance(keyframes, (list, dict)):
        return str(base_val)
    
    if len(keyframes) == 0:
        return str(base_val)

    # Convert to list if it's a dict (some JS libs send objects)
    if isinstance(keyframes, dict):
        keyframes = list(keyframes.values())

    keyframes = sorted(keyframes, key=lambda x: x['t'])

    def get_v(k):
        val = k['v']
        # Handle 2D vectors if axis is provided
        if axis and isinstance(val, dict):
            return val.get(axis, base_val)
        return val

    if len(keyframes) == 1:
        return str(get_v(keyframes[0]))

    # Linear interpolation recursive expression
    expr = str(get_v(keyframes[-1]))
    for i in range(len(keyframes) - 1, 0, -1):
        k1 = keyframes[i-1]
        k2 = keyframes[i]
        t1, v1 = k1['t'], get_v(k1)
        t2, v2 = k2['t'], get_v(k2)
        
        dt = max(0.001, t2 - t1)
        dv = v2 - v1
        interp = f"({v1}+(t-{t1})*({dv}/{dt}))"
        expr = f"if(lt(t,{t2}),{interp},{expr})"

    t1, v1 = keyframes[0]['t'], get_v(keyframes[0])
    return f"if(lt(t,{t1}),{v1},{expr})"

def generate_preset_anim_expr(anim_type, dur, total_dur, base_val, mode='in'):
    if not anim_type or anim_type == 'none': return str(base_val)
    
    if mode == 'in':
        if anim_type == 'fade': return f"min(1, t/{dur})"
        if anim_type == 'pop': return f"if(lt(t,{dur}), {base_val}*(0.5+0.5*(t/{dur})), {base_val})"
        if anim_type == 'slide': return f"if(lt(t,{dur}), {base_val}*(t/{dur}) - 20*(1-(t/{dur})), {base_val})"
    
    if mode == 'out':
        start_out = max(0, total_dur - dur)
        if anim_type == 'fade': return f"if(gt(t,{start_out}), 1-((t-{start_out})/{dur}), 1)"

    return str(base_val)

def get_sec(time_str):
    """Convert HH:MM:SS.ms to float seconds."""
    try:
        if ":" not in time_str: return float(time_str)
        parts = time_str.split(':')
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        return float(time_str)
    except:
        return 0.0

def process_manual_edits(
    input_paths: list,
    output_path: str,
    edits: dict,
    music_path: str = None,
    music_start: float = 0.0,
    music_dur: float = 0.0,
    music_volume: float = 1.0,
    music_offset: float = 0.0,
    progress_callback = None
) -> str:
    # 1. Preparations
    total_dur = 0
    cl_info = []
    for p in input_paths:
        if not os.path.exists(p): raise FileNotFoundError(f"Input video not found: {p}")
        d = get_video_duration(p)
        cl_info.append({'p': p, 'd': d})
        total_dur += d
    
    # Harmonized with Editor.html keys
    speed = float(edits.get('speed', 1.0))
    trim_start = float(edits.get('trimS', 0))
    trim_end = float(edits.get('trimE', total_dur))
    total_trimmed_dur = (trim_end - trim_start) / speed
    
    adjusts = edits.get('adjusts', {})
    vfx = edits.get('vfx', {})
    texts = edits.get('texts', [])
    kf_data = adjusts.get('kf', {})

    # 1. Ratio / Scaling / Concat (Pre-chain)
    pre_chains = []
    ratio_str = edits.get('ratio', 'original')
    
    # Target Res
    tw, th = 1920, 1080 # Default
    if ratio_str == '9:16': tw, th = 1080, 1920
    elif ratio_str == '1:1': tw, th = 1080, 1080
    
    # Build Concat Filter
    concat_v_in = ""
    concat_a_in = ""
    state_clips = edits.get('clips', [])
    
    for i, _ in enumerate(input_paths):
        # Get offset and duration for this specific clip segment
        info = state_clips[i] if i < len(state_clips) else {}
        offset = float(info.get('srcOffset', 0))
        duration = float(info.get('dur', cl_info[i]['d']))
        
        # Apply trim to individual clip before scaling/concat
        # This allows the same source file to be used for multiple segments
        trim_v = f"trim=start={offset}:duration={duration},setpts=PTS-STARTPTS,"
        trim_a = f"atrim=start={offset}:duration={duration},asetpts=PTS-STARTPTS,"
        
        # Scale and pad each clip to match target canvas
        sc_pad = f"{trim_v}scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},setsar=1"
        pre_chains.append(f"[{i}:v]{sc_pad}[v{i}];[{i}:a]{trim_a}aresample=44100[a{i}]")
        concat_v_in += f"[v{i}]"
        concat_a_in += f"[a{i}]"
    
    pre_filter = ";".join(pre_chains) + f";{concat_v_in}{concat_a_in}concat=n={len(input_paths)}:v=1:a=1[basev][basea]"
    
    v_filters = []
    
    # 2. Trim & Speed (on the concatenated stream)
    v_filters.append(f"trim=start={trim_start}:end={trim_end},setpts=PTS-STARTPTS")
    if speed != 1.0: 
        v_filters.append(f"setpts=PTS/{speed}")

    # 3. VFX Overlays & Entrance
    v_in = vfx.get('in', 'none')
    v_in_dur = float(vfx.get('inDur', 0.5))
    if v_in == 'fade':
        v_filters.append(f"fade=t=in:st=0:d={v_in_dur}")
        
    overlay = vfx.get('overlay', 'none')
    if overlay == 'vhs':
        v_filters.append("noise=alls=10:allf=t+u,hue=s=0.3,vignette='PI/4'")
    elif overlay == 'glitch':
        v_filters.append("chromashift=cbh=5:crh=-5,noise=alls=20:allf=t+u")
    elif overlay == 'grain':
        v_filters.append("noise=alls=5:allf=t+u")

    # 4. Color Adjustments (Keyframed)
    # Fix: Ensure default keyframe value is an empty list, NOT an int
    b_expr = generate_ffmpeg_expr(kf_data.get('brightness', []), base_val=adjusts.get('brightness', 100))
    c_expr = generate_ffmpeg_expr(kf_data.get('contrast', []), base_val=adjusts.get('contrast', 100))
    s_expr = generate_ffmpeg_expr(kf_data.get('saturate', []), base_val=adjusts.get('saturate', 100))
    
    v_filters.append(f"eq=brightness=({b_expr}-100)/100:contrast={c_expr}/100:saturation={s_expr}/100")

    # 5. Text Overlays
    for item in texts:
        content = item.get('val', '').replace("'", "").replace(":", "\\:")
        if not content: continue
        
        tkf = item.get('kf', {})
        
        x_base = generate_ffmpeg_expr(tkf.get('t-pos', []), base_val=item.get('x', 50), axis='x')
        y_base = generate_ffmpeg_expr(tkf.get('t-pos', []), base_val=item.get('y', 50), axis='y')
        sz_base = generate_ffmpeg_expr(tkf.get('t-size', []), base_val=item.get('size', 40))
        
        # Entrance Animation Evaluation
        anim_type = item.get('anim', 'none')
        anim_dur = item.get('animDur', 0.5)
        st = item.get('start', 0)
        alpha_expr = "1.0"
        
        if anim_type == 'pop':
            sz_base = f"if(lt(t-{st},{anim_dur}), {sz_base}*(0.1+0.9*((t-{st})/{anim_dur})), {sz_base})"
            alpha_expr = f"min(1, (t-{st})/{anim_dur})"
        elif anim_type == 'zoom':
            sz_base = f"if(lt(t-{st},{anim_dur}), {sz_base}*(3.0 - 2.0*((t-{st})/{anim_dur})), {sz_base})"
            alpha_expr = f"min(1, (t-{st})/{anim_dur})"
        elif anim_type == 'slide':
            y_base = f"if(lt(t-{st},{anim_dur}), {y_base} + 15 - 15*((t-{st})/{anim_dur}), {y_base})"
            alpha_expr = f"min(1, (t-{st})/{anim_dur})"
        elif anim_type == 'fade':
            alpha_expr = f"min(1, (t-{st})/{anim_dur})"
        elif anim_type == 'spin':
            sz_base = f"if(lt(t-{st},{anim_dur}), {sz_base}*((t-{st})/{anim_dur}), {sz_base})"
        
        # Color & BG
        color = item.get('color', '#ffffff').replace('#', '0x')
        if anim_type in ['pop', 'zoom', 'slide', 'fade']:
            # drawtext accepts alpha in fontcolor starting with 0x (hex) and appending @alpha
            color = f"{color}@{alpha_expr}"

        show_bg = 1 if item.get('bg', True) else 0
        raw_font = item.get('font', 'Arial')
        font = raw_font.split(',')[0].replace("'", "").replace('"', '').strip()
        if not font or font.lower() == 'inter': font = 'Arial'
        
        v_filters.append(
            f"drawtext=text='{content}':font='{font}':fontcolor='{color}':fontsize={sz_base}:"
            f"x=({x_base}/100)*w-text_w/2:y=({y_base}/100)*h-text_h/2:"
            f"box={show_bg}:boxcolor=black@0.4:boxborderw=10:borderw=1:bordercolor=black:"
            f"enable='between(t,{item.get('start',0)},{item.get('start',0)+item.get('dur',999)})'"
        )

    a_filters = []
    a_filters.append(f"atrim=start={trim_start}:end={trim_end},asetpts=PTS-STARTPTS")
    if speed != 1.0:
        sv = speed
        while sv > 2.0: a_filters.append("atempo=2.0"); sv /= 2.0
        while sv < 0.5: a_filters.append("atempo=0.5"); sv /= 0.5
        a_filters.append(f"atempo={sv}")

    filter_complex = f"{pre_filter};[basev]{','.join(v_filters)}[outv]"
    
    command = ["ffmpeg", "-y", "-nostdin"]
    for p in input_paths:
        command.extend(["-i", p])

    has_music = music_path and os.path.exists(music_path)
    if has_music:
        command.extend(["-i", music_path])
        m_idx = len(input_paths)
        # Audio mixed pipeline
        delay_ms = int(music_start * 1000)
        filter_complex += f";[basea]{','.join(a_filters)}[main_a];" \
                          f"[{m_idx}:a]atrim=start={music_offset}:duration={music_dur},asetpts=PTS-STARTPTS,volume={music_volume},adelay={delay_ms}|{delay_ms}[music_a];" \
                          f"[main_a][music_a]amix=inputs=2:duration=first:dropout_transition=2[outa]"
    else:
        filter_complex += f";[basea]{','.join(a_filters)}[outa]"

    command.extend([
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "ultrafast", # Faster for preview/manual
        "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        output_path
    ])
    
    # Run with progress tracking
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding='utf-8',
            errors='replace'
        )

        for line in process.stdout:
            # Look for time=00:00:00.00
            if "time=" in line:
                try:
                    time_part = line.split("time=")[1].split(" ")[0]
                    cur_sec = get_sec(time_part)
                    if total_trimmed_dur > 0:
                        progress = min(99, int((cur_sec / total_trimmed_dur) * 100))
                        if progress_callback:
                            progress_callback(progress)
                except:
                    pass
        
        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command)
            
        if progress_callback: progress_callback(100)
    except Exception as e:
        logger.error(f"FFmpeg manual failed: {e}")
        raise e

    return output_path

def get_video_duration(path):
    cmd = [ "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    try: return float(res.stdout.strip())
    except: return 0.0
