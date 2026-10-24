from __future__ import annotations

from typing import Dict, List


SITE_PATTERNS: Dict[str, Dict[str, List[str]]] = {
    "stackoverflow": {
        "patterns": [
            r"(?is)<aside[^>]*class=\"[^\"]*(?:js-sidebar-zone|sidebar|left-sidebar)[^\"]*\"[^>]*>.*?</aside>",
            r"(?is)<div[^>]*id=\"comments\"[^>]*>.*?</div>",
            r"(?is)<div[^>]*class=\"[^\"]*js-consent-banner[^\"]*\"[^>]*>.*?</div>",
        ],
        "rules": ["remove_sidebar", "remove_comments", "remove_consent"],
    },
    "github": {
        "patterns": [
            r"(?is)<header[^>]*>.*?</header>",
            r"(?is)<nav[^>]*>.*?</nav>",
            r"(?is)<footer[^>]*>.*?</footer>",
            r"(?is)<div[^>]*class=\"[^\"]*(?:Layout-sidebar|discussion-sidebar|application-main)[^\"]*\"[^>]*>.*?</div>",
        ],
        "rules": ["remove_header", "remove_nav", "remove_footer", "remove_sidebar"],
    },
    "medium": {
        "patterns": [
            r"(?is)<aside[^>]*>.*?</aside>",
            r"(?is)<div[^>]*class=\"[^\"]*(?:metabar|overlay|recommendations|footer)[^\"]*\"[^>]*>.*?</div>",
            r"(?is)<section[^>]*aria-label=\"[^\"]*(?:More from|Responses)[^\"]*\"[^>]*>.*?</section>",
        ],
        "rules": ["remove_aside", "remove_meta", "remove_recommendation"],
    },
    "reddit": {
        "patterns": [
            r"(?is)<aside[^>]*>.*?</aside>",
            r"(?is)<div[^>]*class=\"[^\"]*(?:sidebar|promotedlink|ads|premium-banner)[^\"]*\"[^>]*>.*?</div>",
            r"(?is)<shreddit-comments[^>]*>.*?</shreddit-comments>",
        ],
        "rules": ["remove_aside", "remove_ads", "remove_comments_widget"],
    },
    "devto": {
        "patterns": [
            r"(?is)<aside[^>]*class=\"[^\"]*(?:crayons-layout__sidebar-left|crayons-layout__sidebar-right)[^\"]*\"[^>]*>.*?</aside>",
            r"(?is)<div[^>]*id=\"comments-container\"[^>]*>.*?</div>",
            r"(?is)<div[^>]*class=\"[^\"]*(?:widget|advertisement)[^\"]*\"[^>]*>.*?</div>",
        ],
        "rules": ["remove_sidebars", "remove_comments", "remove_widgets"],
    },
    "nytimes": {
        "patterns": [
            r"(?is)<header[^>]*>.*?</header>",
            r"(?is)<footer[^>]*>.*?</footer>",
            r"(?is)<section[^>]*id=\"comments\"[^>]*>.*?</section>",
            r"(?is)<div[^>]*data-testid=\"ad\"[^>]*>.*?</div>",
        ],
        "rules": ["remove_header_footer", "remove_comments", "remove_ads"],
    },
    "substack": {
        "patterns": [
            r"(?is)<aside[^>]*>.*?</aside>",
            r"(?is)<div[^>]*class=\"[^\"]*(?:subscribe-widget|footer-wrap|comments)[^\"]*\"[^>]*>.*?</div>",
            r"(?is)<section[^>]*id=\"comments\"[^>]*>.*?</section>",
        ],
        "rules": ["remove_aside", "remove_subscribe", "remove_comments"],
    },
    "wikipedia": {
        "patterns": [
            r"(?is)<header[^>]*>.*?</header>",
            r"(?is)<nav[^>]*>.*?</nav>",
            r"(?is)<footer[^>]*>.*?</footer>",
            r"(?is)<div[^>]*id=\"mw-navigation\"[^>]*>.*?</div>",
            r"(?is)<div[^>]*id=\"mw-panel\"[^>]*>.*?</div>",
            r"(?is)<div[^>]*class=\"[^\"]*(?:vector-header|vector-page-toolbar|vector-footer|mw-footer|mw-editsection)[^\"]*\"[^>]*>.*?</div>",
        ],
        "rules": ["remove_navigation", "remove_toolbar", "remove_footer"],
    },
    "arxiv": {
        "patterns": [
            r"(?is)<header[^>]*>.*?</header>",
            r"(?is)<footer[^>]*>.*?</footer>",
            r"(?is)<div[^>]*id=\"header\"[^>]*>.*?</div>",
            r"(?is)<div[^>]*id=\"footer\"[^>]*>.*?</div>",
            r"(?is)<div[^>]*class=\"[^\"]*(?:extra-services|submission-history|endorsers|footer|header)[^\"]*\"[^>]*>.*?</div>",
        ],
        "rules": ["remove_header_footer", "remove_extras"],
    },
    "hackernews": {
        "patterns": [
            r"(?is)<table[^>]*class=\"[^\"]*fatitem[^\"]*\"[^>]*>.*?</table>",
            r"(?is)<center[^>]*>.*?</center>",
            r"(?is)<tr[^>]*class=\"[^\"]*(?:morespace|spacer)[^\"]*\"[^>]*>.*?</tr>",
        ],
        "rules": ["remove_chrome", "remove_spacers"],
    },
}


def get_site_patch(site: str) -> Dict[str, List[str]]:
    return dict(SITE_PATTERNS.get(str(site or "").strip().lower(), {}))
