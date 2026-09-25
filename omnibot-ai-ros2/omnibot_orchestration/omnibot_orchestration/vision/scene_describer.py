import base64
import io
from typing import TYPE_CHECKING, Optional

import numpy as np

if TYPE_CHECKING:
    from omnibot_orchestration.langchain_agent_node import LangchainAgentNode


class SceneDescriber:
    """
    Converts the robot's latest camera frame to a natural language scene description.

    Two modes (selected by use_claude_vision parameter):
      True  — sends image directly to Claude vision API (claude-sonnet-4-6)
      False — POSTs to the vla_serve /predict endpoint
    """

    _SCENE_PROMPT = (
        "You are the vision system of a mobile manipulation robot. "
        "Describe this scene concisely: what objects are present, "
        "their approximate positions relative to the robot, and any "
        "notable features. Focus on objects that could be manipulation "
        "targets. Keep the description under 100 words."
    )

    def __init__(
        self,
        node: "LangchainAgentNode",
        use_claude_vision: bool,
        vla_serve_url: str,
        anthropic_api_key: str,
    ):
        self._node = node
        self._use_claude_vision = use_claude_vision
        self._vla_serve_url = vla_serve_url.rstrip("/")
        self._api_key = anthropic_api_key or None

        # Lazy import so the node can start even if anthropic is not installed
        self._anthropic_client = None
        if use_claude_vision:
            try:
                import anthropic

                self._anthropic_client = anthropic.Anthropic(api_key=self._api_key)
            except ImportError:
                node.get_logger().warn(
                    "anthropic package not installed — scene description will fail. "
                    "Run: pip install anthropic"
                )

    def describe_scene(self, camera: str = "front") -> str:
        """Synchronous — must be called from a worker thread, not the ROS spin thread."""
        image_np = self._get_image(camera)
        if image_np is None:
            return (
                f"No image available from the {camera} camera. "
                "The camera may not be publishing yet."
            )

        b64_jpeg = self._numpy_to_base64_jpeg(image_np)

        if self._use_claude_vision:
            return self._describe_with_claude(b64_jpeg)
        return self._describe_with_vla_serve(b64_jpeg)

    def _get_image(self, camera: str) -> Optional[np.ndarray]:
        with self._node._image_lock:
            if camera == "wrist":
                img = self._node._latest_wrist_image
            else:
                img = self._node._latest_front_image
        return img

    @staticmethod
    def _numpy_to_base64_jpeg(img: np.ndarray) -> str:
        from PIL import Image as PILImage

        pil = PILImage.fromarray(img.astype(np.uint8))
        buf = io.BytesIO()
        pil.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _describe_with_claude(self, b64_jpeg: str) -> str:
        if self._anthropic_client is None:
            return "Claude vision unavailable (anthropic package not installed)."
        try:
            import anthropic

            response = self._anthropic_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=512,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": b64_jpeg,
                                },
                            },
                            {"type": "text", "text": self._SCENE_PROMPT},
                        ],
                    }
                ],
            )
            return response.content[0].text
        except anthropic.APIError as e:
            return f"Claude vision API error: {e}"
        except Exception as e:
            return f"Scene description failed: {e}"

    def _describe_with_vla_serve(self, b64_jpeg: str) -> str:
        import requests

        try:
            resp = requests.post(
                f"{self._vla_serve_url}/predict",
                json={
                    "image_base64": b64_jpeg,
                    "instruction": "Describe the scene. What objects do you see?",
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("raw_output") or str(data.get("action", ""))
            return raw if raw else "vla_serve returned an empty description."
        except requests.exceptions.ConnectionError:
            return (
                f"Cannot reach vla_serve at {self._vla_serve_url}. "
                "Ensure the VLA inference server is running."
            )
        except requests.RequestException as e:
            return f"vla_serve scene query failed: {e}"
