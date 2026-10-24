from __future__ import annotations

import subprocess
import logging
import sys
import pkg_resources
from typing import List, Set, Optional

logger = logging.getLogger(__name__)

class DependencyHealer:
    """
    Auto-detects and installs missing Python dependencies.
    Helps L3 brain self-heal from ImportErrors.
    """
    
    # SAFE LIST: Only allow installation of these trusted packages
    ALLOWED_PACKAGES = {
        "pandas", "numpy", "matplotlib", "seaborn", "scikit-learn", 
        "requests", "httpx", "beautifulsoup4", "lxml",
        "pillow", "opencv-python", "pyautogui", "playwright",
        "networkx", "sympy", "torch", "transformers", "fastapi", "uvicorn"
    }

    @staticmethod
    def list_installed() -> Set[str]:
        return {pkg.key for pkg in pkg_resources.working_set}

    @staticmethod
    def find_missing(required: List[str]) -> List[str]:
        installed = DependencyHealer.list_installed()
        return [r for r in required if r.lower() not in installed]

    @staticmethod
    def install_packages(packages: List[str]) -> bool:
        """Attempts to pip install missing packages if they are allowed."""
        if not packages:
            return True
            
        # 1. Security Check
        safe_packages = []
        for pkg in packages:
            if pkg.lower() in DependencyHealer.ALLOWED_PACKAGES:
                safe_packages.append(pkg)
            else:
                logger.warning(f"Self-Healing: Blocked installation of untrusted package '{pkg}'")
        
        if not safe_packages:
            return False

        logger.info(f"Self-Healing: Installing safe packages: {safe_packages}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *safe_packages])
            return True
        except Exception as e:
            logger.error(f"Self-Healing: Installation failed: {e}")
            return False

    @staticmethod
    def heal_from_error(error_msg: str) -> bool:
        """
        Parses an ImportError message and tries to install the missing module.
        Example: "No module named 'pandas'"
        """
        import re
        match = re.search(r"No module named '([^']+)'", error_msg)
        if match:
            module_name = match.group(1)
            # Note: mapping module name to pip package name can be tricky
            # This is a simplified best-effort approach.
            return DependencyHealer.install_packages([module_name])
        return False

# Global instance
dependency_healer = DependencyHealer()
