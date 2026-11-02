# app/cms/utils/sanitize.py
# Allow-list HTML sanitizer for post/page `content` (backed by nh3, a Rust port of ammonia).
# Applied on WRITE (create/update) so stored content is always safe to render with innerHTML.
#
# What survives: common editorial markup (headings, lists, tables, links, images, code, quotes).
# What is removed: <script>/<style>/<iframe>/<object>/<form>, event handlers (onclick=...),
# inline `style`, and any URL scheme other than http/https/mailto/tel (so `javascript:` and
# `data:` links/images are dropped). Links get rel="noopener noreferrer".
import nh3

from app.cms.config import SANITIZE_HTML

ALLOWED_TAGS = {
    "p", "br", "hr", "div", "span",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "s", "del", "ins", "sub", "sup", "mark", "small",
    "blockquote", "pre", "code",
    "ul", "ol", "li",
    "a", "img", "figure", "figcaption",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
}

ALLOWED_ATTRIBUTES = {
    "*": {"class", "id", "lang", "dir", "title"},
    # NOTE: `rel` must not be listed here; nh3 injects it via link_rel below.
    "a": {"href", "target", "hreflang"},
    "img": {"src", "alt", "width", "height", "loading"},
    "th": {"colspan", "rowspan", "scope"},
    "td": {"colspan", "rowspan"},
}

ALLOWED_URL_SCHEMES = {"http", "https", "mailto", "tel"}


def sanitize_html(value):
    """Return `value` with all unsafe markup removed. None stays None; idempotent."""
    if value is None or not SANITIZE_HTML:
        return value
    return nh3.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer",
        strip_comments=True,
    )
