from __future__ import annotations

class BrowserCleaner:
    """
    P5: Ported from OpenClaw's injected cleaner.
    Removes annoying popups, overlays, and sticky banners before AI perception.
    """
    
    CLEAN_JS = """
    () => {
        const removeBySelectors = (selectors) => {
            selectors.forEach(s => {
                document.querySelectorAll(s).forEach(el => {
                    el.style.display = 'none';
                    el.style.setProperty('display', 'none', 'important');
                });
            });
        };

        // 1. Common clutter selectors
        removeBySelectors([
            '.modal', '.overlay', '.popup', '.cookie-banner', 
            '[id*="cookie"]', '[class*="modal-backdrop"]',
            '.ad-container', '#newsletter-signup'
        ]);

        // 2. Heavy-duty Overlay Detection (OpenClaw Parity)
        const vh = window.innerHeight;
        const vw = window.innerWidth;
        
        document.querySelectorAll('*').forEach(el => {
            const style = window.getComputedStyle(el);
            if (style.position === 'fixed' || style.position === 'absolute') {
                const rect = el.getBoundingClientRect();
                const area = rect.width * rect.height;
                // If it covers more than 40% of the screen and has a high z-index
                if (area > (vh * vw * 0.4) && parseInt(style.zIndex) > 5) {
                    el.style.display = 'none';
                }
            }
        });

        // 3. Unlock Body Scroll
        document.body.style.overflow = 'auto';
        document.body.style.setProperty('overflow', 'auto', 'important');
        document.documentElement.style.overflow = 'auto';
    }
    """
