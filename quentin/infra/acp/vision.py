from __future__ import annotations

import logging
import base64
import io
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
from .skills import MobileSkillBridge
from quentin.llm.client import call_llm

logger = logging.getLogger(__name__)

class MobileVisionManager:
    """
    Handles visual understanding of the mobile screen.
    Uses 'Set-of-Mark' (SoM) to label UI elements with numbers for high-precision control.
    Ported from OpenClaw's advanced media understanding pipeline.
    """
    def __init__(self, node_id: str):
        self.node_id = node_id

    def _apply_som_labels(self, b64_image: str, ui_elements: List[Dict[str, Any]]) -> Tuple[str, Dict[int, Dict]]:
        """
        Draws numbered boxes on the image and returns a mapping of number -> element.
        """
        img_data = base64.b64decode(b64_image)
        img = Image.open(io.BytesIO(img_data))
        draw = ImageDraw.Draw(img)
        
        # Best-effort font loading
        try:
            # Common paths for Linux/macOS
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        except:
            font = ImageFont.load_default()

        id_map = {}
        for i, el in enumerate(ui_elements, start=1):
            bounds = el.get("bounds") # Expected [x, y, w, h]
            if not bounds or len(bounds) < 4: continue
            
            x, y, w, h = bounds
            # Draw bounding box
            draw.rectangle([x, y, x + w, y + h], outline="red", width=3)
            # Draw label background
            label_w, label_h = 35, 30
            draw.rectangle([x, y - label_h, x + label_w, y], fill="red")
            # Draw number
            draw.text((x + 5, y - label_h), str(i), fill="white", font=font)
            
            id_map[i] = el

        # Export back to Base64
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=80)
        return base64.b64encode(buffered.getvalue()).decode('utf-8'), id_map

    def _extract_interactive_elements(self, tree: Any) -> List[Dict[str, Any]]:
        """
        Flattens the UI hierarchy into a list of interactable elements with bounds.
        Recursive logic to find all buttons, inputs, etc.
        """
        elements = []
        
        def walk(node):
            if not isinstance(node, dict): return
            
            # If node has bounds and looks interactable (simplified heuristic)
            if "bounds" in node and node.get("role") in ("button", "link", "textbox", "checkbox"):
                elements.append(node)
            
            for child in node.get("children", []) or []:
                walk(child)
        
        walk(tree)
        return elements

    async def analyze_and_act(self, goal: str) -> str:
        """
        The refined Vision-Action Loop:
        1. Capture raw screen & tree.
        2. Filter and Number elements (SoM).
        3. Brain sees the 'numbered' map and picks a label.
        """
        logger.info(f"Vision: Capturing and numbering screen for goal: {goal}")
        
        raw_b64 = await MobileSkillBridge.get_screenshot(self.node_id)
        ui_tree = await MobileSkillBridge.get_ui_tree(self.node_id)
        
        elements = self._extract_interactive_elements(ui_tree)
        labeled_b64, id_map = self._apply_som_labels(raw_b64, elements)

        # 3. Call the real Multimodal LLM
        prompt = (
            f"GOAL: {goal}\n\n"
            "SYSTEM STATE (UI Tree): \n"
            f"{str(ui_tree)[:2000]}\n\n"
            "VISUAL GUIDE:\n"
            "I have labeled all interactable elements on the attached screenshot with RED NUMBERS.\n"
            "Identify the correct element to achieve the goal.\n"
            "Respond ONLY with JSON: {\"target_id\": <number>, \"action\": \"click|type\", \"text\": \"...\", \"reason\": \"...\"}"
        )
        
        try:
            # call_llm now supports images!
            result_json = call_llm(
                config="gemini-1.5-flash", # Example multimodal model
                user_prompt=prompt,
                images=[labeled_b64],
                actor="vision_manager"
            )
            return result_json
        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            return f"Error: {str(e)}"

    async def stream_to_canvas(self):
        """Streaming with overlays placeholder."""
        pass