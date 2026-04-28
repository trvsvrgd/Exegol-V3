import os
import shutil
from typing import Optional, List, Dict
from playwright.sync_api import sync_playwright

def record_interaction(url: str, output_dir: str, duration_seconds: int = 5, actions: Optional[List[Dict]] = None) -> str:
    """
    Records a web interaction using Playwright and saves the resulting video.
    
    Args:
        url: The web URL to navigate to.
        output_dir: The directory where the video will be saved.
        duration_seconds: How long to record (in seconds).
        actions: Optional list of actions to perform on the page (e.g., clicks, scrolls).
    
    Returns:
        The path to the saved video file.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            record_video_dir=output_dir,
            record_video_size={"width": 1280, "height": 720}
        )
        page = context.new_page()
        
        try:
            page.goto(url)
            
            if actions:
                for action in actions:
                    act_type = action.get("type")
                    target = action.get("target")
                    if act_type == "click" and target:
                        page.click(target)
                    elif act_type == "type" and target:
                        page.fill(target, action.get("value", ""))
                    elif act_type == "scroll":
                        page.mouse.wheel(0, action.get("value", 500))
                    page.wait_for_timeout(1000)
            
            page.wait_for_timeout(duration_seconds * 1000)
            video_path = page.video.path()
            
        finally:
            context.close()
            browser.close()
            
        return video_path
