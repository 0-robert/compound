from moviepy import VideoFileClip
import os

class VideoEditor:
    def __init__(self, target_size=(256, 256), target_fps=30):
        self.target_size = target_size
        self.target_fps = target_fps

    def process_video(self, input_path, output_path, start_offset=0):
        """
        Resizes the video to target_size, sets the target_fps, and trims the start.
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input video not found: {input_path}")

        clip = VideoFileClip(input_path)
        
        # Trim the start if an offset is provided
        if start_offset > 0:
            # moviepy 2.x subclipped
            clip = clip.subclipped(start_time=start_offset)

        # Resize and set fps
        processed_clip = clip.resized(new_size=self.target_size).with_fps(self.target_fps)
        
        # Write to file
        processed_clip.write_videofile(
            output_path, 
            codec="libx264", 
            audio=False, 
            fps=self.target_fps,
            logger=None # Suppress moviepy output
        )
        
        clip.close()
        processed_clip.close()
        
        return output_path
