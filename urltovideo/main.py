import asyncio
import os
import sys
from url_to_video import URLRecorder, VideoEditor

async def main():
    # Configuration
    url = "https://www.apple.com" # Example URL
    if len(sys.argv) > 1:
        url = sys.argv[1]
    
    raw_output_dir = "recordings_raw"
    final_output_path = "output_scroll.mp4"
    
    print(f"Starting recording of {url}...")
    recorder = URLRecorder(output_dir=raw_output_dir, viewport_size={"width": 1024, "height": 1024})
    
    try:
        # 1. Record the video (15 seconds scroll)
        result = await recorder.record_scroll(url, duration=15)
        raw_video_path = result["video_path"]
        page_text = result["text"]
        start_offset = result["scroll_start_offset"]
        
        print(f"Raw video recorded at: {raw_video_path}")
        print(f"Extracted {len(page_text)} characters of text.")
        print(f"Detected scroll start offset: {start_offset:.2f}s")
        
        # 2. Edit the video (256x256, 30fps)
        print("Processing video (trimming white start)...")
        editor = VideoEditor(target_size=(256, 256), target_fps=30)
        editor.process_video(raw_video_path, final_output_path, start_offset=start_offset)
        
        print(f"Final video saved to: {final_output_path}")
        
        # Final combined output for user/backend reference
        final_result = {
            "text": page_text,
            "video_path": os.path.abspath(final_output_path)
        }
        print("\nFinal Result Dictionary:")
        print(final_result)
        
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())
