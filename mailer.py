import base64
import os
from datetime import date
from io import BytesIO
from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image

SECTION_ORDER = ["MLOps / ModelOps", "LLMOps / AgentOps", "Kubernetes & Compute", "Research"]

SECTION_COLORS = {
    "MLOps / ModelOps":       "#2563eb",
    "LLMOps / AgentOps":      "#7c3aed",
    "Kubernetes & Compute":   "#059669",
    "Research":               "#d97706",
}

_IMAGE_CID  = "pheme-hero"
_LOGO_CID   = "pheme-logo"
_README_CID = "pheme-readme"

_BASE_DIR = Path(__file__).parent
_jinja_env = Environment(
    loader=select_autoescape(["html"]),
    autoescape=select_autoescape(["html"]),
)
_jinja_env.loader = FileSystemLoader(_BASE_DIR / "templates")


def _load_logo() -> bytes | None:
    """Load the Pheme logo, invert colours to white and make background transparent."""
    logo_path = _BASE_DIR / "assets" / "pheme-logo.png"
    if not logo_path.exists():
        return None
    img = Image.open(logo_path).convert("RGBA")
    pixels = list(img.getdata())
    new_pixels = []
    for r, g, b, a in pixels:
        brightness = (r + g + b) / 3
        if brightness > 180:          # white / near-white → transparent
            new_pixels.append((0, 0, 0, 0))
        else:                         # dark lines → white
            new_pixels.append((255, 255, 255, 255))
    img.putdata(new_pixels)
    img.thumbnail((128, 128), Image.LANCZOS)
    out = BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _render_html(
    newsletter: dict,
    today: str,
    has_image: bool,
    has_logo: bool,
    has_readme: bool,
) -> str:
    items_by_section: dict[str, list] = {s: [] for s in SECTION_ORDER}
    for item in newsletter.get("items", []):
        sec = item.get("section", "Research")
        if sec not in items_by_section:
            sec = "Research"
        items_by_section[sec].append(item)

    template = _jinja_env.get_template("daily.html")
    return template.render(
        date=today,
        total=len(newsletter.get("items", [])),
        intro=newsletter.get("intro", ""),
        sections=SECTION_ORDER,
        items_by_section=items_by_section,
        section_colors=SECTION_COLORS,
        has_image=has_image,
        image_cid=_IMAGE_CID,
        has_logo=has_logo,
        logo_cid=_LOGO_CID,
        repo=newsletter.get("repo_of_day"),
        has_readme=has_readme,
        readme_cid=_README_CID,
        server_url=os.environ.get("SERVER_URL", "http://localhost:8765"),
    )


def send_newsletter(
    newsletter: dict,
    image_bytes: bytes | None = None,
    readme_bytes: bytes | None = None,
    recipient: str = "pablo.escobardelaoliva@outlook.com",
) -> None:
    resend.api_key = os.environ["RESEND_API_KEY"]

    today      = date.today().strftime("%B %d, %Y")
    logo_bytes = _load_logo()
    html       = _render_html(
        newsletter, today,
        has_image=image_bytes is not None,
        has_logo=logo_bytes is not None,
        has_readme=readme_bytes is not None,
    )

    def _attachment(content: bytes, filename: str, mime: str, cid: str) -> dict:
        return {
            "content":      base64.b64encode(content).decode(),
            "filename":     filename,
            "content_type": mime,
            "content_id":   cid,
            "disposition":  "inline",
        }

    attachments = []
    if logo_bytes:
        attachments.append(_attachment(logo_bytes,   "pheme-logo.png", "image/png",  _LOGO_CID))
    if image_bytes:
        attachments.append(_attachment(image_bytes,  "hero.jpg",       "image/jpeg", _IMAGE_CID))
    if readme_bytes:
        attachments.append(_attachment(readme_bytes, "readme.jpg",     "image/jpeg", _README_CID))

    params: resend.Emails.SendParams = {
        "from":        os.environ.get("RESEND_FROM", "Pheme <onboarding@resend.dev>"),
        "to":          [recipient],
        "subject":     f"Pheme — {today}",
        "html":        html,
        "attachments": attachments,
    }

    result = resend.Emails.send(params)
    print(f"  Email sent: {result.get('id', result)}")
