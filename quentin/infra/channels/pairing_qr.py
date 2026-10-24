from __future__ import annotations

import qrcode
import io
from typing import Optional

class PairingQR:
    """
    Generates terminal-based ASCII QR codes for easy mobile pairing.
    Ported from OpenClaw's pairing-messages.ts.
    """
    
    @staticmethod
    def generate_terminal_qr(pairing_code: str, node_id: str) -> str:
        """
        Creates a QR code representing the pairing URL.
        """
        # Format: quentin://pair?code=ABC123&node=xxxx
        data = f"quentin://pair?code={pairing_code}&node={node_id}"
        
        qr = qrcode.QRCode(version=1, border=1)
        qr.add_data(data)
        qr.make(fit=True)
        
        # Capture ASCII representation
        f = io.StringIO()
        qr.print_ascii(out=f)
        return f.getvalue()

# Global helper
