"""Persona presets and persistence for persona-targeted demo generation.

A persona bundles a single block of guidance that steers BOTH stages of the
pipeline: how the exploration agent browses the app (what to dig into) and how the
scriptwriter frames the narration (what to emphasise, which outcomes to sell). The
eight presets below are defaults defined in code; user edits are persisted to
``config/personas.json`` and merged over the defaults at load time, so a persona can
always be reverted to its shipped default by deleting its saved entry.
"""

import json
import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STORE_PATH = os.path.join(_REPO_ROOT, "config", "personas.json")

# Universal storytelling scaffold applied to every persona (including General). It
# distils widely used frameworks — StoryBrand (audience is the hero, product is the
# guide), the Heath brothers' "Made to Stick" SUCCESs (Simple, Unexpected, Concrete,
# Credible, Emotional, Stories), and the contrast arc from the Pixar Story Spine /
# Duarte "sparkline" (what is vs. what could be). Each persona then layers on the
# specific techniques that resonate most with that audience.
STORYTELLING_FRAMEWORK = (
    "Craft the narration as a story, not a feature tour. Apply these techniques:\n"
    "- Cast the VIEWER as the hero and the product as the guide that helps them win — "
    "never make the product the hero of its own story.\n"
    "- Open with a hook that names the audience's real-world pain or ambition before "
    "showing any UI.\n"
    "- Establish stakes early: what does it cost the viewer to keep doing things the "
    "old way?\n"
    "- Follow a clear arc — setup (the problem), rising tension (why it's hard today), "
    "resolution (how the product changes that), and payoff (the outcome they win). "
    "Alternate between 'what is' (today's friction) and 'what could be' (life with the "
    "product) to create contrast and pull.\n"
    "- Keep the core message SIMPLE (one memorable takeaway), make claims CONCRETE and "
    "CREDIBLE (tie every claim to something visible on screen), and land at least one "
    "EMOTIONAL beat — people remember how a demo made them feel.\n"
    "- Use the rule of three when listing benefits; keep momentum with tight, spoken "
    "sentences.\n"
    "- Use callbacks — reference the opening pain at the close so the story lands.\n"
    "- End on an emotional payoff and one crisp, persona-appropriate call to action.\n"
    "Keep it authentic and confident; never oversell or invent capabilities."
)

# Each preset: id -> {name, description, instructions}
DEFAULT_PERSONAS = {
    "general": {
        "name": "General / No persona",
        "description": "Balanced, audience-agnostic demo. Matches the default behaviour.",
        "instructions": "",
    },
    "cto": {
        "name": "CTO",
        "description": "Technical depth — architecture, APIs, performance, scale.",
        "instructions": (
            "Audience: a CTO or senior engineering leader evaluating this product for "
            "their stack.\n"
            "While exploring, dig into anything that reveals technical substance: "
            "architecture, integrations and APIs, extensibility, data model, "
            "performance and latency cues, scalability, reliability, developer "
            "experience, configurability, and admin/observability surfaces. Prefer "
            "screens that show how the system actually works over marketing surfaces.\n"
            "When narrating, speak to engineering credibility: explain how it fits into "
            "an existing architecture, where it saves engineering effort, how it scales, "
            "and how it reduces operational risk. Be precise and use correct technical "
            "vocabulary, but stay outcome-oriented — a CTO cares about velocity, "
            "maintainability, and total system health, not just features.\n"
            "Storytelling techniques that land with a CTO: show, don't tell — prove "
            "claims with live behaviour and real specifics (Concrete + Credible) rather "
            "than adjectives; use before/after contrast between a brittle status-quo "
            "architecture and the cleaner path with this in place; respect their "
            "expertise by skipping hype and earning trust with precise, verifiable "
            "detail; keep one simple throughline — the single biggest engineering win."
        ),
    },
    "ceo": {
        "name": "CEO",
        "description": "Vision & ROI — business outcomes, growth, differentiation.",
        "instructions": (
            "Audience: a CEO or business leader deciding whether this moves the needle "
            "for the company.\n"
            "While exploring, focus on features that map to business outcomes: revenue "
            "growth, market differentiation, speed to value, team productivity, "
            "customer experience, and strategic capabilities. Note anything that signals "
            "competitive advantage or measurable impact.\n"
            "When narrating, lead with vision and outcomes. Frame each capability in "
            "terms of growth, competitive edge, and return on investment. Keep technical "
            "detail light; translate features into business value and momentum. Paint "
            "the bigger picture of where the company can go with this in place.\n"
            "Storytelling techniques that land with a CEO: paint a vivid 'what could "
            "be' — the transformed future the company reaches with this in place, "
            "contrasted against the cost of standing still; anchor the whole story to "
            "one simple, memorable strategic idea; use the rule of three for the "
            "headline outcomes; close on momentum and an aspirational call to action."
        ),
    },
    "ciso": {
        "name": "CISO",
        "description": "Security & compliance — data protection, audit, risk.",
        "instructions": (
            "Audience: a CISO or security leader assessing risk before adoption.\n"
            "While exploring, prioritise security-relevant surfaces: authentication and "
            "SSO, access controls and roles/permissions, audit logs, data handling and "
            "encryption cues, privacy settings, compliance/certification references, "
            "admin governance, and anything touching sensitive data. Capture screens "
            "that demonstrate control and visibility.\n"
            "When narrating, speak to trust and risk reduction: how the product protects "
            "data, enforces least privilege, provides auditability, and supports "
            "compliance. Be measured and precise; a CISO values evidence of control, "
            "transparency, and defensible posture over hype.\n"
            "Storytelling techniques that land with a CISO: frame stakes through loss "
            "aversion — make the risk of the status quo real (what a breach or gap "
            "would cost) without fear-mongering, then resolve it with visible controls; "
            "build trust through transparency by showing the control actually working "
            "(Concrete + Credible); contrast exposure-before with defensible-posture-"
            "after; keep every claim evidence-based, never hand-wavy."
        ),
    },
    "cfo": {
        "name": "CFO",
        "description": "Cost & financial impact — TCO, efficiency, payback.",
        "instructions": (
            "Audience: a CFO or finance leader scrutinising the financial case.\n"
            "While exploring, look for anything tied to cost and efficiency: automation "
            "that removes manual work, consolidation of tools, usage/reporting and "
            "analytics, forecasting, and features that reduce headcount pressure or "
            "operational spend. Note where time or money is demonstrably saved.\n"
            "When narrating, frame value in financial terms: total cost of ownership, "
            "efficiency gains, payback period, and measurable savings. Quantify impact "
            "wherever the UI makes it credible, and connect each capability to the "
            "bottom line. Keep it grounded and specific — avoid vague promises.\n"
            "Storytelling techniques that land with a CFO: make it Concrete and "
            "Credible with real numbers — quantify the before/after wherever the UI "
            "allows; use loss-aversion framing (the ongoing cost of waste and manual "
            "effort) balanced with the gain; contrast today's spend against the "
            "optimised path; distil it to one simple financial takeaway they could "
            "repeat to the board."
        ),
    },
    "practitioner": {
        "name": "End User / Practitioner",
        "description": "Day-to-day usability & workflow for the hands-on user.",
        "instructions": (
            "Audience: the hands-on person who will use this product every day.\n"
            "While exploring, walk the real workflows a practitioner performs: how a "
            "task starts and finishes, how many steps it takes, what shortcuts and "
            "quality-of-life touches exist, and where the product removes friction. "
            "Favour the screens they'll actually live in.\n"
            "When narrating, be warm, concrete, and practical. Show how the product "
            "makes their day easier — fewer clicks, less busywork, faster results — and "
            "narrate as if walking a colleague through it. Emphasise ease, clarity, and "
            "the satisfying moments of getting work done.\n"
            "Storytelling techniques that land with a practitioner: tell a 'day in the "
            "life' story with them as the hero — a relatable moment of friction that "
            "the product resolves; use vivid, concrete, sensory detail about the actual "
            "task; contrast the tedious before with the effortless after; land an "
            "emotional payoff — the relief and satisfaction of finishing work faster."
        ),
    },
    "product_manager": {
        "name": "Product Manager",
        "description": "Workflow fit, integrations, and roadmap alignment.",
        "instructions": (
            "Audience: a product manager evaluating fit, adoption, and how this slots "
            "into their team's workflow.\n"
            "While exploring, focus on end-to-end workflows, integrations with other "
            "tools, collaboration features, configurability, analytics that inform "
            "decisions, and signals of extensibility or roadmap direction. Note how the "
            "product would fit an existing process.\n"
            "When narrating, connect capabilities to team outcomes: faster iteration, "
            "better cross-functional collaboration, clearer insight into what's working. "
            "Frame the product as part of a workflow, not an island, and highlight how "
            "it adapts to how teams already work.\n"
            "Storytelling techniques that land with a PM: walk an end-to-end journey "
            "(story-spine style: 'every day the team… until the product…') with their "
            "team as the hero; contrast a fragmented, hand-off-heavy process against one "
            "connected flow; make it Concrete with a real decision the data unlocks; "
            "keep one simple throughline about how the team ships better."
        ),
    },
    "investor": {
        "name": "Investor / Board",
        "description": "Market, traction, and defensible moat.",
        "instructions": (
            "Audience: an investor or board member gauging the strength and potential of "
            "the business behind this product.\n"
            "While exploring, look for signals of product maturity, differentiation, "
            "breadth and depth of capability, and anything suggesting stickiness or a "
            "defensible moat. Note what would be hard for a competitor to replicate.\n"
            "When narrating, tell the market story: the size of the problem, how this "
            "product wins, why it's differentiated, and where the growth and durability "
            "come from. Speak to traction and potential; keep it strategic and "
            "confident, connecting the demo to the investment thesis.\n"
            "Storytelling techniques that land with an investor: lead with a 'why now' "
            "market narrative and a bold 'what could be' vision, contrasted against the "
            "old world being disrupted; use traction and proof points to make the thesis "
            "Credible; distil everything to one Simple, memorable thesis; close on "
            "momentum and the size of the prize."
        ),
    },
    "sales_champion": {
        "name": "Sales Champion / Buyer",
        "description": "Value pitch to help a champion convince their org.",
        "instructions": (
            "Audience: an internal champion who liked the product and now needs to sell "
            "it to their own organisation.\n"
            "While exploring, gather the concrete proof points a champion needs: "
            "standout capabilities, quick wins, features that address common objections, "
            "and moments that create an obvious 'wow'. Note what makes an undeniable "
            "case.\n"
            "When narrating, arm the champion with a persuasive, repeatable pitch: the "
            "core value in a sentence, the top differentiators, and answers to the "
            "objections their stakeholders will raise. Make it easy for them to retell "
            "this story and win internal buy-in.\n"
            "Storytelling techniques that arm a champion: hand them a Simple, repeatable "
            "one-liner and a 'three reasons' structure they can retell from memory; cast "
            "their organisation as the hero and the champion as the guide who brings the "
            "win; pre-empt and neutralise the objections their stakeholders will raise "
            "(name the villain, then defeat it); back each point with a concrete "
            "quick-win proof point so the case feels undeniable."
        ),
    },
}


def _load_store():
    """Return the persisted overrides dict ({persona_id: {instructions: ...}})."""
    if not os.path.isfile(_STORE_PATH):
        return {}
    try:
        with open(_STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_store(store):
    os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
    tmp = _STORE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _STORE_PATH)


def load_personas():
    """Return all personas as an ordered list, merging saved edits over defaults."""
    store = _load_store()
    personas = []
    for pid, preset in DEFAULT_PERSONAS.items():
        saved = store.get(pid) or {}
        instructions = saved.get("instructions", preset["instructions"])
        personas.append(
            {
                "id": pid,
                "name": preset["name"],
                "description": preset["description"],
                "instructions": instructions,
                "is_default": "instructions" not in saved,
            }
        )
    return personas


def get_persona(persona_id):
    """Return a single persona dict (merged) or None if the id is unknown."""
    if persona_id not in DEFAULT_PERSONAS:
        return None
    for persona in load_personas():
        if persona["id"] == persona_id:
            return persona
    return None


def save_persona(persona_id, instructions):
    """Persist edited instructions for a preset. Returns the updated persona."""
    if persona_id not in DEFAULT_PERSONAS:
        raise KeyError(persona_id)
    store = _load_store()
    entry = store.get(persona_id) or {}
    entry["instructions"] = instructions
    store[persona_id] = entry
    _save_store(store)
    return get_persona(persona_id)


def reset_persona(persona_id):
    """Revert a preset to its shipped default. Returns the default persona."""
    if persona_id not in DEFAULT_PERSONAS:
        raise KeyError(persona_id)
    store = _load_store()
    if persona_id in store:
        del store[persona_id]
        _save_store(store)
    return get_persona(persona_id)
