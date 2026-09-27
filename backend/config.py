import os
from dataclasses import dataclass, field
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]

@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv('VISIONGUARD_DATA', ROOT / 'data')))
    ollama_url: str = field(default_factory=lambda: os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434'))
    model: str = field(default_factory=lambda: os.getenv('AGENT_MODEL', 'qwen3:4b'))
    vision_model: str = field(default_factory=lambda: os.getenv('VISION_MODEL', 'qwen2.5vl:3b'))
    approval_token: str = field(default_factory=lambda: os.getenv('VISIONGUARD_APPROVAL_TOKEN') or secrets.token_urlsafe(24))
    device_mode: str = field(default_factory=lambda: os.getenv('DEVICE_MODE', 'mock'))
    mqtt_host: str = field(default_factory=lambda: os.getenv('MQTT_HOST', '127.0.0.1'))
    mqtt_port: int = field(default_factory=lambda: int(os.getenv('MQTT_PORT', '1884')))
    yolo_weights: str = field(default_factory=lambda: os.getenv('YOLO_WEIGHTS', str(ROOT / 'models' / 'yolo11n.pt')))

