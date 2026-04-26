# URL-to-Video Scroller Agent Toolkit

A specialized Python package designed for automated agents and backends to capture website content. It opens a URL, performs a smooth programmatic scroll to the bottom, extracts all page text, and exports a processed 256x256 @ 30fps MP4 video.

## Capabilities
- **Browser Automation**: Uses Playwright (Chromium) for high-fidelity rendering.
- **Content Extraction**: Retrieves `document.body.innerText` for semantic analysis.
- **Smooth Scrolling**: Programmatic vertical scrolling over a defined duration.
- **Video Post-Processing**: Automatically scales and retimes video to 256x256, 30fps, MP4.

## Setup for Agents
1. **Environment**: Python 3.8+
2. **Installation**:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

## Integration Reference

### Primary Entry Point: `URLRecorder.record_scroll`
**Method Signature**: `async def record_scroll(self, url: str, duration: int = 15) -> dict`

**Returns**:
```json
{
  "text": "Extracted website text contents...",
  "video_path": "/absolute/path/to/raw/video.webm"
}
```

### Post-Processing: `VideoEditor.process_video`
**Method Signature**: `def process_video(self, input_path: str, output_path: str) -> str`

**Behavior**: Converts any input video to `256x256`, `30fps`, `MP4 (H.264)`.

## Example Usage
```python
import asyncio
from url_to_video import URLRecorder, VideoEditor

async def run():
    # 1. Capture Raw Content
    recorder = URLRecorder(output_dir="recordings_raw")
    data = await recorder.record_scroll("https://apple.com", duration=15)
    
    # 2. Process for Backend Requirements
    editor = VideoEditor(target_size=(256, 256), target_fps=30)
    final_video_path = "final_output.mp4"
    editor.process_video(data["video_path"], final_video_path)
    
    # Final Payload
    payload = {
        "text": data["text"],
        "video_path": final_video_path
    }
    return payload

asyncio.run(run())
```

## Directory Structure
- `url_to_video/recorder.py`: `URLRecorder` class (Playwright logic).
- `url_to_video/editor.py`: `VideoEditor` class (MoviePy logic).
- `main.py`: CLI wrapper for testing.
- `requirements.txt`: Dependency list.
- `.gitignore`: Configured to exclude `venv`, raw recordings, and output videos.
