import os
from typing import Optional

def clip_video(input_path: str, output_path: str, start_time: int = 0, duration: Optional[int] = None, speed: float = 1.0) -> str:
    """
    Clips and processes a video (e.g. for creating a fast, short UAT loop).
    
    Args:
        input_path: Path to the input video file.
        output_path: Path to save the processed video (can be .mp4, .gif, or .webm).
        start_time: Start time in seconds.
        duration: Duration to keep in seconds. If None, keeps until the end.
        speed: Speed multiplier (e.g. 2.0 for 2x fast forward).
    
    Returns:
        The path to the output video.
    """
    from moviepy import VideoFileClip, vfx

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input video not found: {input_path}")
        
    clip = VideoFileClip(input_path)
    
    if duration is not None:
        clip = clip.subclip(start_time, start_time + duration)
    elif start_time > 0:
        clip = clip.subclip(start_time)
        
    if speed != 1.0:
        clip = clip.with_effects([vfx.MultiplySpeed(speed)])
        
    if output_path.lower().endswith(".gif"):
        clip.write_gif(output_path, fps=10)
    else:
        clip.write_videofile(output_path, codec="libx264", audio_codec="aac")
        
    clip.close()
    return output_path
