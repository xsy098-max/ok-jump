import os
import time

import cv2


class ScreenshotHelper:
    
    def __init__(self, screenshots_folder="screenshots"):
        self.screenshots_folder = screenshots_folder
        self._ensure_folder()
    
    def _ensure_folder(self):
        if not os.path.exists(self.screenshots_folder):
            os.makedirs(self.screenshots_folder)
    
    def save_screenshot(self, frame, name=None, prefix="screenshot"):
        if frame is None:
            return None
        
        if name is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            name = f"{prefix}_{timestamp}.png"
        
        if not name.endswith('.png'):
            name = f"{name}.png"
        
        filepath = os.path.join(self.screenshots_folder, name)
        cv2.imwrite(filepath, frame)
        return filepath
    
    def save_feature_template(self, frame, x, y, width, height, feature_name):
        if frame is None:
            return None
        
        template = frame[y:y+height, x:x+width]
        
        features_folder = os.path.join(self.screenshots_folder, "features")
        if not os.path.exists(features_folder):
            os.makedirs(features_folder)
        
        filepath = os.path.join(features_folder, f"{feature_name}.png")
        cv2.imwrite(filepath, template)
        return filepath
    
    @staticmethod
    def get_coco_annotation(image_id, category_id, x, y, width, height, annotation_id):
        return {
            "id": annotation_id,
            "image_id": image_id,
            "category_id": category_id,
            "bbox": [x, y, width, height],
            "area": width * height,
            "iscrowd": 0
        }
    
    @staticmethod
    def get_coco_image_entry(image_id, filename, height, width):
        return {
            "id": image_id,
            "file_name": filename,
            "height": height,
            "width": width
        }


screenshot_helper = ScreenshotHelper()
