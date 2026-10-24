from __future__ import annotations

import logging
from typing import List, Dict, Any
from quentin.infra.browser.skills import BrowserSkills
from quentin.infra.mobile.adb_client import adb_client
from quentin.infra.desktop.skills import DesktopSkills
from quentin.infra.acp.skills import MobileSkillBridge

logger = logging.getLogger(__name__)

class BuiltinSkillProvider:
    """
    Exposes all INFRA-level capabilities as high-level Quentin Skills.
    This is the 'nerve cluster' connecting brain to body.
    """
    
    @staticmethod
    def get_definitions() -> List[Dict[str, Any]]:
        """Returns enhanced skill definitions with usage examples."""
        return [
            # 1. Browser Skills
            {
                "skill_id": "browser.open", 
                "description": "Open a URL in the automated browser.",
                "example": "await browser.open(url='https://google.com')"
            },
            {
                "skill_id": "browser.click", 
                "description": "Click an element by CSS selector.",
                "example": "await browser.click(selector='button#submit')"
            },
            {
                "skill_id": "browser.type", 
                "description": "Type text into a web input field.",
                "example": "await browser.type(selector='input[name=\"q\"]', text='Quentin AI')"
            },
            
            # 2. Mobile (Android/ADB) Skills
            {
                "skill_id": "mobile.tap", 
                "description": "Tap at normalized (0-1) coordinates on Android.",
                "example": "await mobile.tap(x=0.5, y=0.8) # Taps bottom-center"
            },
            {
                "skill_id": "mobile.screenshot", 
                "description": "Capture Android screen for visual analysis.",
                "example": "await mobile.screenshot()"
            },
            
            # 3. Desktop Skills
            {
                "skill_id": "desktop.click", 
                "description": "Perform physical mouse click on the computer screen.",
                "example": "await desktop.click(x=500, y=300)"
            },
            
            # 4. Coding & Self-Programming Skills
            {
                "skill_id": "coder.generate",
                "description": "Call a specialized coding CLI (Gemini, Claude Code, Codex) to solve a programming problem.",
                "example": "await coder.generate(goal='Implement auth middleware', instructions='Use JWT and handle token expiration', context_files=['src/auth.py'], backend='gemini_cli')"
            },
            {
                "skill_id": "gemini.code",
                "description": "Fast-track coding task specifically using Gemini CLI.",
                "example": "await gemini.code(prompt='Write a python script to parse logs')"
            },
            {
                "skill_id": "claude.code",
                "description": "Fast-track coding task specifically using Claude Code CLI.",
                "example": "await claude.code(prompt='Fix the memory leak in the buffer manager')"
            }
        ]

    @staticmethod
    async def execute(skill_id: str, args: Dict[str, Any]) -> Any:
        """Dispatches execution to the correct infra adapter with ID resolution."""
        
        # 0. Sanitize Arguments (Atomic Parity)
        from quentin.infra.tools.sanitizer import sanitizer
        args = sanitizer.sanitize(skill_id, args)

        # 1. Handle SoM ID Resolution (The Magic Glue)
        target_id = str(args.get("target_id", ""))
        som_map = args.get("metadata", {}).get("som_id_map", {})
        
        if target_id and target_id in som_map:
            element = som_map[target_id]
            bounds = element.get("bounds", [0, 0, 0, 0])
            # Calculate center point
            args["x"] = bounds[0] + bounds[2] / 2
            args["y"] = bounds[1] + bounds[3] / 2
            # For browser, we might need the selector
            args["selector"] = element.get("id") or element.get("name")

        # 2. Mapping Skill IDs to Infra Implementations
        if skill_id == "browser.open": return await BrowserSkills.open_url(args.get("url"))
        if skill_id == "browser.click": return await BrowserSkills.click_element(args.get("selector"))
        if skill_id == "browser.type": return await BrowserSkills.type_text(args.get("selector"), args.get("text"))
        
        if skill_id == "mobile.tap": 
            return adb_client.normalized_tap(args.get("x"), args.get("y"))
        if skill_id == "mobile.screenshot":
            return adb_client.get_screenshot()
            
        if skill_id == "desktop.click":
            return await DesktopSkills.click(args.get("x"), args.get("y"))

        # 3. Coding Skill Dispatch
        if skill_id in ("coder.generate", "gemini.code", "claude.code"):
            from meta_agent.tools.coder.router import coder_router
            from meta_agent.tools.coder.base import CodeGenerationRequest
            
            backend = args.get("backend", "gemini_cli")
            if skill_id == "gemini.code": backend = "gemini_cli"
            if skill_id == "claude.code": backend = "claude_code_cli"
            
            prompt = args.get("instructions") or args.get("prompt") or args.get("goal", "")
            context_files = args.get("context_files", [])
            
            req = CodeGenerationRequest(
                goal=args.get("goal", "Coding Task"),
                instructions=prompt,
                context_files=context_files
            )
            res = coder_router.generate(req, backend_name=backend)
            return {
                "success": res.success,
                "code": res.code,
                "reasoning": res.reasoning,
                "backend": backend
            }
            
        raise ValueError(f"Unknown builtin skill: {skill_id}")

# This will be integrated into the Executor's dispatch logic
