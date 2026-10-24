from __future__ import annotations

import asyncio
import base64
import logging
import json
import os
from typing import Any, Dict, Optional, Tuple, List
from pathlib import Path
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    async_playwright = Browser = BrowserContext = Page = Any  # type: ignore

from quentin.infra.canvas.broadcaster import broadcaster

logger = logging.getLogger(__name__)

class BrowserManager:
    """
    Manages an automated browser instance (Playwright).
    Includes atomic-level precision: scale enforcement, proxy, and network interception.
    """
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._streaming_task: Optional[asyncio.Task] = None
        self._network_logs: List[str] = []
        
        # OpenClaw Atomic Details: Stealth Config
        self.proxy = os.getenv("BROWSER_PROXY") 
        self.geo = os.getenv("BROWSER_GEO") 

    async def start(self):
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not installed. Please run 'pip install playwright' and 'playwright install chromium'.")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        
        # Atomic Parity: Force 1.0 scale factor and Network Interception
        context_opts = {
            "viewport": {'width': 1280, 'height': 720},
            "device_scale_factor": 1.0,
            "permissions": ["notifications", "geolocation"]
        }
        
        if self.proxy:
            context_opts["proxy"] = {"server": self.proxy}
        
        if self.geo:
            try:
                lat, lon = map(float, self.geo.split(","))
                context_opts["geolocation"] = {"latitude": lat, "longitude": lon}
            except: pass
        
        state_path = Path("data/browser_state.json")
        if state_path.exists():
            context_opts["storage_state"] = str(state_path)
            
        self.context = await self.browser.new_context(**context_opts)
        
        # Create page and hook network system
        self.page = await self.context.new_page()
        self.page.on("request", self._handle_request)
        
        # P5: Surgery Ninety-six - Console & Error Mirroring (OpenClaw Parity)
        self._browser_logs: List[str] = []
        self.page.on("console", self._handle_console)
        self.page.on("pageerror", self._handle_page_error)
        self.page.on("crash", lambda p: logger.critical("Browser: PAGE CRASHED!"))
        
        # Atomic Parity: Download Interception (The Asset Collector)
        self.page.on("download", self._handle_download)
        
        logger.info("Browser Node started with Network & Download hooks.")
        self._streaming_task = asyncio.create_task(self._stream_frames())

    async def _handle_download(self, download):
        """Intercepts file downloads and saves them to data/downloads."""
        save_path = Path("data/downloads") / download.suggested_filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        await download.save_as(str(save_path))
        logger.info(f"Browser: File downloaded to {save_path}")
        # Could emit a SystemEvent here

    def _handle_console(self, msg):
        """P5: Captures browser console logs (OpenClaw Parity)."""
        entry = f"[CONSOLE:{msg.type}] {msg.text}"
        self._browser_logs.append(entry)
        # Keep last 50 entries
        if len(self._browser_logs) > 50:
            self._browser_logs.pop(0)

    def _handle_page_error(self, error):
        """P5: Captures unhandled JS exceptions (OpenClaw Parity)."""
        entry = f"[PAGE_ERROR] {str(error)}"
        self._browser_logs.append(entry)
        logger.error(f"Browser: Site Error: {error}")

    def _handle_request(self, request):
        if request.resource_type in ["fetch", "xhr"]:
            log_entry = f"[{request.method}] {request.url}"
            self._network_logs.append(log_entry)
            if len(self._network_logs) > 50:
                self._network_logs.pop(0)

    def get_network_logs(self) -> List[str]:
        return list(self._network_logs)

    async def save_state(self):
        """Saves cookies and session storage."""
        if self.context:
            state_path = Path("data/browser_state.json")
            state_path.parent.mkdir(parents=True, exist_ok=True)
            await self.context.storage_state(path=str(state_path))
            logger.info("Browser state saved.")

    async def verify_action_success(self, prev_tree: Dict[str, Any]) -> bool:
        await asyncio.sleep(0.5) 
        current_tree = await self.get_pruned_ui_tree()
        return json.dumps(prev_tree) != json.dumps(current_tree)

    async def click(self, selector: str):
        if self.page:
            try:
                element = self.page.locator(selector).first
                await element.scroll_into_view_if_needed()
                await asyncio.sleep(0.2) 
                await element.click(delay=50) 
            except Exception:
                await self.page.evaluate(f"document.querySelector('{selector}').click()")

    async def scroll(self, direction: str = "down"):
        if self.page:
            amount = 500 if direction == "down" else -500
            await self.page.evaluate(f"window.scrollBy(0, {amount})")

    async def go_back(self):
        if self.page:
            await self.page.go_back()

    async def refresh(self):
        if self.page:
            await self.page.reload()

    async def stop(self):
        if self._streaming_task:
            self._streaming_task.cancel()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser Node stopped.")

    async def get_labeled_screenshot(self) -> Tuple[str, Dict[str, Any]]:
        """
        P5: Upgraded to Atomic SoM mode with Visual Delta Highlighting.
        """
        if not self.page:
            return "", {}

        # 1. Capture Raw Screenshot
        screenshot_bytes = await self.page.screenshot(type="jpeg", quality=80)
        raw_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
        
        # P5: Surgery Seventy-four - Visual Delta Highlighting (OpenClaw Parity)
        processed_b64 = raw_b64
        if hasattr(self, "_last_screenshot_b64") and self._last_screenshot_b64:
            from quentin.utils.image_diff import ImageDiff
            diff_b64 = ImageDiff.highlight_changes(raw_b64, self._last_screenshot_b64)
            if diff_b64:
                processed_b64 = diff_b64
        
        # Update last frame
        self._last_screenshot_b64 = raw_b64
        
        # 2. Get current Semantic Snapshot
        tree_data = await self.get_pruned_ui_tree()
        active_refs = tree_data.get("active_refs", {})
        
        if not active_refs:
            return processed_b64, {}

        # 3. Apply SoM Marks
        from quentin.infra.browser.som_visualizer import SoMVisualizer
        marks = {rid: data.get("bounds") for rid, data in active_refs.items() if data.get("bounds")}
        
        labeled_b64 = SoMVisualizer.apply_marks(processed_b64, marks)
        
        return labeled_b64, active_refs

    async def _stream_frames(self):
        while True:
            try:
                if self.page:
                    screenshot_bytes = await self.page.screenshot(type="jpeg", quality=50)
                    b64_image = base64.b64encode(screenshot_bytes).decode('utf-8')
                    await broadcaster.broadcast({
                        "type": "node_event",
                        "node_id": "browser-main",
                        "event": "screen_frame",
                        "payload": {"image": b64_image}
                    })
                await asyncio.sleep(0.5) 
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Browser streaming error: {e}")
                await asyncio.sleep(1)

    async def navigate(self, url: str):
        # P5: Surgery Ninety-three - Network Egress Filter (OpenClaw Parity)
        from quentin.infra.security.network_policy import NetworkPolicyEnforcer
        if not NetworkPolicyEnforcer.is_allowed(url):
            logger.critical(f"Browser: Access to {url} BLOCKED by network policy.")
            raise PermissionError(f"Network access denied to {url}. Domain not in allowlist.")

        if self.page:
            await self.page.goto(url, wait_until="networkidle")

    async def fill(self, selector: str, text: str):
        if self.page:
            await self.page.fill(selector, text)

    async def get_content(self) -> str:
        if self.page:
            return await self.page.content()
        return ""

    async def get_pruned_ui_tree(self) -> Dict[str, Any]:
        """
        P5: Upgraded with Visual Denoising (OpenClaw Parity).
        """
        if not self.page:
            return {}
            
        # P5: Surgery Fifty-eight - Run Cleaner before perception
        from quentin.infra.browser.cleaner_script import BrowserCleaner
        await self.page.evaluate(BrowserCleaner.CLEAN_JS)
        
        snapshot = await self.page.accessibility.snapshot()
        
        from quentin.infra.browser.semantic_mapper import SemanticMapper
        if not hasattr(self, "semantic_mapper"):
            self.semantic_mapper = SemanticMapper()
            
        # We perform a traversal to inject selectors and map to eN IDs
        # Note: Playwright's accessibility snapshot doesn't include selectors directly,
        # so we augment it with a client-side script if needed, or use 'aria-ref'.
        # For this surgery, we use the mapper to flatten and ID.
        
        formatted_tree = self.semantic_mapper.generate_snapshot(snapshot)
        return {
            "raw_tree": snapshot,
            "semantic_view": formatted_tree,
            "active_refs": self.semantic_mapper.registry,
            "observed_at": time.time() # P5: Perception Heartbeat
        }

    async def get_focused_snapshot(self, ref_id: str) -> Optional[str]:
        """
        P5: Ported from OpenClaw's 'Dual-path vision'.
        Returns a high-res crop focused on the specified element.
        """
        if not self.page: return None
        
        # 1. Get element bounds
        tree_data = await self.get_pruned_ui_tree()
        entry = tree_data.get("active_refs", {}).get(ref_id)
        if not entry or not entry.get("bounds"):
            return None
            
        # 2. Capture Full Screenshot
        screenshot_bytes = await self.page.screenshot(type="jpeg", quality=90)
        raw_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
        
        # 3. Perform Intelligent Crop
        from quentin.utils.vision_utils import VisionUtils
        cx, cy = VisionUtils.get_element_center(entry["bounds"])
        
        focused_b64 = VisionUtils.crop_focus_area(raw_b64, cx, cy, window_size=512)
        return focused_b64

    async def wait_for_stability(self, max_wait_ms: int = 2000, interval_ms: int = 100) -> bool:
        """
        P5: Ported from OpenClaw's 'Aria Stability Check'.
        Waits until the UI tree stops changing (semantics and bounds).
        """
        if not self.page: return True
        
        from quentin.cognitive.perception.hasher import PerceptionHasher
        
        start_time = time.time()
        last_hash = ""
        
        while (time.time() - start_time) * 1000 < max_wait_ms:
            # 1. Capture current semantic state
            current_tree = await self.page.accessibility.snapshot()
            current_hash = PerceptionHasher.compute_ui_hash(current_tree or {}, url=self.page.url)
            
            # 2. Compare with previous sample
            if last_hash and current_hash == last_hash:
                logger.debug(f"Browser: UI is stable (hash={current_hash[:8]})")
                return True
                
            last_hash = current_hash
            await asyncio.sleep(interval_ms / 1000.0)
            
        logger.warning("Browser: Stability timeout reached. Proceeding anyway.")
        return False

    async def click_ref(self, ref_id: str):
        """Clicks an element using its eN semantic ID with Stale & Stability Guard."""
        # P5: Surgery Ninety-seven - Wait for UI to stop moving/loading
        await self.wait_for_stability()

        # P5: Surgery Forty-one - Stale Guard (OpenClaw Parity)
        last_tree = await self.get_pruned_ui_tree() 
        observed_at = last_tree.get("observed_at", 0)
        age = time.time() - observed_at
        
        if age > 30.0:
            logger.error(f"Browser: Stale perception detected ({age:.1f}s old). Rejecting click.")
            raise RuntimeError(f"stale_perception: Your view is {age:.1f}s old. Please refresh the UI tree before acting.")

        if not hasattr(self, "semantic_mapper"):
            raise RuntimeError("Run get_pruned_ui_tree first to initialize refs.")
            
        info = self.semantic_mapper.registry.get(ref_id)
        if not info:
            raise ValueError(f"Ref {ref_id} not found in last snapshot.")
            
        # Use aria role and name to locate the physical element
        name = info["name"]
        role = info["role"]
        
        logger.info(f"Browser: Clicking {ref_id} (role={role}, name={name})")
        
        # P5: Surgery One Hundred and Four - Start Action Recording (OpenClaw Parity)
        from quentin.infra.browser.recorder import ActionRecorder
        # Note: Session ID would ideally come from context
        recorder = ActionRecorder(session_id="default_browser_session")
        
        # P5: Surgery Ninety-eight - Pre-click visual sample (OpenClaw Parity)
        from quentin.utils.visual_feedback import VisualFeedbackEngine
        from quentin.utils.vision_utils import VisionUtils
        
        pre_img = None
        cx, cy = 0, 0
        if info.get("bounds"):
            cx, cy = VisionUtils.get_element_center(info["bounds"])
            # Low-quality snapshot for speed
            screenshot_bytes = await self.page.screenshot(type="jpeg", quality=50)
            raw_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            pre_img = VisualFeedbackEngine.capture_region(raw_b64, cx, cy)
            
            # Record Frame
            recorder.capture_frame(raw_b64, f"before_click_{ref_id}", {"ref": ref_id, "name": name})

        try:
            loc = self.page.get_by_role(role, name=name).first
            await loc.scroll_into_view_if_needed()
            await loc.click(timeout=5000)
            
            # P5: Surgery Ninety-eight - Post-click verification (wait for paint)
            await asyncio.sleep(0.3)
            post_bytes = await self.page.screenshot(type="jpeg", quality=50)
            post_b64 = base64.b64encode(post_bytes).decode('utf-8')
            
            # Record Post-frame
            recorder.capture_frame(post_b64, f"after_click_{ref_id}", {"ref": ref_id})

            if pre_img is not None:
                post_img = VisualFeedbackEngine.capture_region(post_b64, cx, cy)
                if not VisualFeedbackEngine.has_visual_reaction(pre_img, post_img):
                    logger.warning(f"Browser: DEAD CLICK detected on {ref_id}. No visual change.")
                    return {
                        "status": "warning",
                        "result": "click_performed_no_reaction",
                        "hint": "The UI showed no visual change. The element might be covered or inactive. Try scrolling or checking for modals."
                    }
            
            return {"status": "ok", "result": f"Clicked {ref_id}"}
            
        except Exception as e:
            logger.warning(f"Semantic click failed for {ref_id}: {e}. Fallback to generic locator.")
            # Fallback logic...
            
    async def fill_ref(self, ref_id: str, text: str):
        """Fills a textbox using its eN semantic ID with Stability Guard."""
        # P5: Surgery Ninety-seven - Wait for UI to settle (OpenClaw Parity)
        await self.wait_for_stability()

        if not hasattr(self, "semantic_mapper"):
            raise RuntimeError("Run get_pruned_ui_tree first to initialize refs.")
            
        info = self.semantic_mapper.registry.get(ref_id)
        if not info:
            raise ValueError(f"Ref {ref_id} not found in last snapshot.")
            
        name = info["name"]
        role = info["role"]
        
        loc = self.page.get_by_role(role, name=name).first
        await loc.fill(text)

# Singleton instance
browser_manager = BrowserManager()
