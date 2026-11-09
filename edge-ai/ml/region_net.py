"""Optional PyTorch dependency. Imported only for explicit multisignal training/runtime."""
import cv2
import numpy as np
import torch
from torch import nn
from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small

from ml.regions import IMAGE_SIZE

MODEL_FORMAT = "mobilenet-eye-mouth-v1"
MEAN = np.asarray([.485, .456, .406], dtype=np.float32)[:, None, None]
STD = np.asarray([.229, .224, .225], dtype=np.float32)[:, None, None]


def image_tensor(image):
    if image is None:
        raise ValueError("Missing region image")
    rgb = cv2.cvtColor(cv2.resize(image, (IMAGE_SIZE, IMAGE_SIZE)), cv2.COLOR_BGR2RGB)
    return torch.from_numpy((rgb.transpose(2, 0, 1).astype(np.float32) / 255 - MEAN) / STD)


class RegionNet(nn.Module):
    def __init__(self, pretrained=False):
        super().__init__()
        base = mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.DEFAULT if pretrained else None)
        self.features = base.features
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.eye_head = nn.Linear(576, 2)
        self.mouth_head = nn.Linear(576, 3)

    def forward(self, image):
        embedding = self.pool(self.features(image)).flatten(1)
        return self.eye_head(embedding), self.mouth_head(embedding)


def load_region_net(path, device="cpu"):
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if checkpoint.get("format") != MODEL_FORMAT:
        raise ValueError("Unsupported region network format")
    network = RegionNet()
    network.load_state_dict(checkpoint["state_dict"], strict=True)
    network.to(device).eval()
    return network
