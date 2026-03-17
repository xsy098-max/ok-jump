from ok import og


class ResolutionAdapter:
    
    REFERENCE_WIDTH = 1920
    REFERENCE_HEIGHT = 1080
    SUPPORTED_RATIO = 16 / 9
    
    def __init__(self):
        self._current_width = 0
        self._current_height = 0
        self._scale_x = 1.0
        self._scale_y = 1.0
        self._is_valid_resolution = False
        
        self._load_config()
    
    def _load_config(self):
        config = getattr(og, 'config', None)
        if config:
            ref_res = config.get('reference_resolution', {})
            if ref_res:
                self.REFERENCE_WIDTH = ref_res.get('width', 1920)
                self.REFERENCE_HEIGHT = ref_res.get('height', 1080)
            
            supported = config.get('supported_resolution', {})
            if 'ratio' in supported:
                ratio_str = supported['ratio']
                if ':' in ratio_str:
                    w, h = ratio_str.split(':')
                    self.SUPPORTED_RATIO = float(w) / float(h)
    
    def update_resolution(self, width, height):
        self._current_width = width
        self._current_height = height
        
        self._scale_x = width / self.REFERENCE_WIDTH
        self._scale_y = height / self.REFERENCE_HEIGHT
        
        current_ratio = width / height if height > 0 else 0
        self._is_valid_resolution = abs(current_ratio - self.SUPPORTED_RATIO) < 0.01
        
        return self._is_valid_resolution
    
    def scale_x(self, x):
        return int(x * self._scale_x)
    
    def scale_y(self, y):
        return int(y * self._scale_y)
    
    def scale_point(self, x, y):
        return (self.scale_x(x), self.scale_y(y))
    
    def scale_width(self, width):
        return int(width * self._scale_x)
    
    def scale_height(self, height):
        return int(height * self._scale_y)
    
    def scale_box(self, x, y, width, height):
        return (
            self.scale_x(x),
            self.scale_y(y),
            self.scale_width(width),
            self.scale_height(height)
        )
    
    def to_relative(self, x, y):
        if self._current_width <= 0 or self._current_height <= 0:
            return (0, 0)
        return (x / self._current_width, y / self._current_height)
    
    def to_relative_box(self, x, y, width, height):
        if self._current_width <= 0 or self._current_height <= 0:
            return (0, 0, 0, 0)
        return (
            x / self._current_width,
            y / self._current_height,
            width / self._current_width,
            height / self._current_height
        )
    
    def from_relative(self, rel_x, rel_y):
        return (int(rel_x * self._current_width), int(rel_y * self._current_height))
    
    def from_relative_box(self, rel_x, rel_y, rel_width, rel_height):
        return (
            int(rel_x * self._current_width),
            int(rel_y * self._current_height),
            int(rel_width * self._current_width),
            int(rel_height * self._current_height)
        )
    
    def get_scale_factor(self):
        return (self._scale_x, self._scale_y)
    
    def is_valid_resolution(self):
        return self._is_valid_resolution
    
    def get_current_resolution(self):
        return (self._current_width, self._current_height)
    
    def get_reference_resolution(self):
        return (self.REFERENCE_WIDTH, self.REFERENCE_HEIGHT)
    
    def check_aspect_ratio(self, width=None, height=None):
        if width is None:
            width = self._current_width
        if height is None:
            height = self._current_height
        
        if width <= 0 or height <= 0:
            return False, 0
        
        current_ratio = width / height
        ratio_diff = abs(current_ratio - self.SUPPORTED_RATIO)
        
        return ratio_diff < 0.01, ratio_diff
    
    def get_recommended_resize(self, width=None, height=None):
        if width is None:
            width = self._current_width
        if height is None:
            height = self._current_height
        
        config = getattr(og, 'config', None)
        if config:
            supported = config.get('supported_resolution', {})
            resize_options = supported.get('resize_to', [])
            
            for target_w, target_h in resize_options:
                if target_w <= width and target_h <= height:
                    return (target_w, target_h)
        
        if width >= 2560:
            return (2560, 1440)
        elif width >= 1920:
            return (1920, 1080)
        elif width >= 1600:
            return (1600, 900)
        else:
            return (1280, 720)
    
    @property
    def width(self):
        return self._current_width
    
    @property
    def height(self):
        return self._current_height
    
    @property
    def scale_x_ratio(self):
        return self._scale_x
    
    @property
    def scale_y_ratio(self):
        return self._scale_y


resolution_adapter = ResolutionAdapter()
