"""
ONNX YOLOv11 检测器

用于战场单位识别（自己、友方、敌军、死亡状态）和勾选框识别
参考 ok-wuthering-waves 实现
"""

import numpy as np
import cv2

try:
    import onnxruntime as ort
except ImportError:
    ort = None


class OnnxYoloDetect:
    """
    YOLOv11 ONNX 检测器
    
    通用目标检测器，可用于：
    - 战场单位检测：
      - 自己 (label=0)
      - 友方 (label=1)
      - 敌军 (label=2)
      - 死亡状态 (label=3)
      - 目标圈 (label=4)
    - 勾选框检测：
      - 已勾选 (label=0)
      - 未勾选 (label=1)
    """
    
    def __init__(self, weights, conf_threshold=0.25, iou_threshold=0.45):
        """
        初始化检测器
        
        Args:
            weights: ONNX 模型路径
            conf_threshold: 置信度阈值
            iou_threshold: NMS IOU 阈值
        """
        if ort is None:
            raise ImportError("onnxruntime 未安装，请运行: pip install onnxruntime")
        
        self.weights = weights
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        
        # 创建推理会话
        providers = ['CPUExecutionProvider']
        try:
            # 尝试使用 GPU
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        except:
            pass
        
        self.session = ort.InferenceSession(weights, providers=providers)
        
        # 获取模型输入输出信息
        self.input_name = self.session.get_inputs()[0].name
        self.input_shape = self.session.get_inputs()[0].shape
        self.output_names = [o.name for o in self.session.get_outputs()]
        
        # 模型输入尺寸（默认 640x640）
        self.input_width = self.input_shape[3] if len(self.input_shape) >= 4 else 640
        self.input_height = self.input_shape[2] if len(self.input_shape) >= 4 else 640
    
    def preprocess(self, image):
        """
        预处理图像
        
        Args:
            image: BGR 图像 (numpy array)
            
        Returns:
            preprocessed: 预处理后的图像
            ratio: 缩放比例
            pad: 填充量 (pad_w, pad_h)
        """
        img_height, img_width = image.shape[:2]
        
        # 计算缩放比例
        ratio = min(self.input_width / img_width, self.input_height / img_height)
        
        # 计算新尺寸
        new_width = int(img_width * ratio)
        new_height = int(img_height * ratio)
        
        # 缩放图像
        resized = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
        
        # 计算填充量
        pad_w = (self.input_width - new_width) // 2
        pad_h = (self.input_height - new_height) // 2
        
        # 创建填充后的图像
        padded = np.full((self.input_height, self.input_width, 3), 114, dtype=np.uint8)
        padded[pad_h:pad_h+new_height, pad_w:pad_w+new_width] = resized
        
        # BGR -> RGB
        padded = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
        
        # 归一化并转换为 NCHW 格式
        preprocessed = padded.astype(np.float32) / 255.0
        preprocessed = preprocessed.transpose(2, 0, 1)  # HWC -> CHW
        preprocessed = np.expand_dims(preprocessed, axis=0)  # 添加 batch 维度
        
        return preprocessed, ratio, (pad_w, pad_h)
    
    def postprocess(self, outputs, ratio, pad, conf_threshold=None, label=-1):
        """
        后处理检测结果
        
        Args:
            outputs: 模型输出
            ratio: 缩放比例
            pad: 填充量 (pad_w, pad_h)
            conf_threshold: 置信度阈值
            label: 过滤特定标签 (-1 表示不过滤)
            
        Returns:
            detections: 检测结果列表 [(x, y, w, h, conf, class_id), ...]
        """
        if conf_threshold is None:
            conf_threshold = self.conf_threshold
        
        pad_w, pad_h = pad
        
        # YOLOv11 输出格式: (1, 84, N) 或 (1, N, 84)
        # 84 = 4 (bbox) + 80 (classes) 或 4 + num_classes
        output = outputs[0]
        
        # 检查输出形状并转置如果需要
        if output.shape[1] < output.shape[2]:
            output = output.transpose(0, 2, 1)
        
        # output shape: (1, N, 4 + num_classes)
        output = output[0]  # 移除 batch 维度
        
        # 分离边界框和类别分数
        num_classes = output.shape[1] - 4
        boxes = output[:, :4]  # cx, cy, w, h
        scores = output[:, 4:]  # 类别分数
        
        detections = []
        
        for i in range(len(boxes)):
            # 获取最高置信度的类别
            class_scores = scores[i]
            class_id = np.argmax(class_scores)
            conf = class_scores[class_id]
            
            # 置信度过滤
            if conf < conf_threshold:
                continue
            
            # 标签过滤
            if label >= 0 and class_id != label:
                continue
            
            # 获取边界框 (cx, cy, w, h) -> (x1, y1, x2, y2)
            cx, cy, w, h = boxes[i]
            x1 = cx - w / 2
            y1 = cy - h / 2
            x2 = cx + w / 2
            y2 = cy + h / 2
            
            # 去除填充并还原到原始尺寸
            x1 = (x1 - pad_w) / ratio
            y1 = (y1 - pad_h) / ratio
            x2 = (x2 - pad_w) / ratio
            y2 = (y2 - pad_h) / ratio
            
            detections.append(DetectionResult(
                x=int(x1),
                y=int(y1),
                width=int(x2 - x1),
                height=int(y2 - y1),
                confidence=float(conf),
                class_id=int(class_id)
            ))
        
        # NMS 非极大值抑制
        detections = self._nms(detections)
        
        return detections
    
    def _nms(self, detections):
        """
        非极大值抑制
        
        Args:
            detections: 检测结果列表
            
        Returns:
            过滤后的检测结果
        """
        if not detections:
            return detections
        
        # 按置信度排序
        detections = sorted(detections, key=lambda x: x.confidence, reverse=True)
        
        keep = []
        while detections:
            current = detections.pop(0)
            keep.append(current)
            
            detections = [
                d for d in detections
                if d.class_id != current.class_id or 
                self._iou(current, d) < self.iou_threshold
            ]
        
        return keep
    
    def _iou(self, box1, box2):
        """
        计算两个框的 IOU
        """
        x1 = max(box1.x, box2.x)
        y1 = max(box1.y, box2.y)
        x2 = min(box1.x + box1.width, box2.x + box2.width)
        y2 = min(box1.y + box1.height, box2.y + box2.height)
        
        inter_area = max(0, x2 - x1) * max(0, y2 - y1)
        
        box1_area = box1.width * box1.height
        box2_area = box2.width * box2.height
        
        iou = inter_area / (box1_area + box2_area - inter_area + 1e-6)
        return iou
    
    def detect(self, image, threshold=None, label=-1):
        """
        执行检测
        
        Args:
            image: BGR 图像 (numpy array)
            threshold: 置信度阈值 (None 使用默认值)
            label: 过滤特定标签 (-1 表示不过滤)
            
        Returns:
            detections: 检测结果列表 [DetectionResult, ...]
        """
        if threshold is None:
            threshold = self.conf_threshold
        
        # 预处理
        preprocessed, ratio, pad = self.preprocess(image)
        
        # 推理
        outputs = self.session.run(self.output_names, {self.input_name: preprocessed})
        
        # 后处理
        detections = self.postprocess(outputs, ratio, pad, threshold, label)
        
        return detections


class DetectionResult:
    """
    检测结果类
    
    存储单个检测结果的信息
    """
    
    def __init__(self, x, y, width, height, confidence, class_id):
        """
        初始化检测结果
        
        Args:
            x: 左上角 x 坐标
            y: 左上角 y 坐标
            width: 宽度
            height: 高度
            confidence: 置信度
            class_id: 类别 ID
        """
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.confidence = confidence
        self.class_id = class_id
    
    @property
    def center_x(self):
        """获取中心点 x 坐标"""
        return self.x + self.width // 2
    
    @property
    def center_y(self):
        """获取中心点 y 坐标"""
        return self.y + self.height // 2
    
    @property
    def center(self):
        """获取中心点 (x, y)"""
        return (self.center_x, self.center_y)
    
    @property
    def box(self):
        """获取边界框 (x, y, w, h)"""
        return (self.x, self.y, self.width, self.height)
    
    @property
    def xyxy(self):
        """获取边界框 (x1, y1, x2, y2)"""
        return (self.x, self.y, self.x + self.width, self.y + self.height)
    
    def __repr__(self):
        return (f"DetectionResult(x={self.x}, y={self.y}, w={self.width}, h={self.height}, "
                f"conf={self.confidence:.2f}, class_id={self.class_id})")
