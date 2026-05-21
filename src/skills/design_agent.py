"""Design agent — interactive HTML designer that asks questions first.

Flow:
  1. Emit agent_question events (style, sections, colors, RTL)
  2. Wait for each answer via answer_bus
  3. Build a rich design context string
  4. Delegate to html_artifact with that context
"""

from __future__ import annotations

from typing import Any

from ..core.answer_bus import register, wait_answer
from ..utils.event_bus import Event, bus

_QUESTIONS = [
    {
        "question_id": "style",
        "question": "ما أسلوب التصميم المفضل لديك؟",
        "field_type": "single",
        "options": [
            {"value": "modern",    "label": "عصري وأنيق",     "icon": "✨"},
            {"value": "minimal",   "label": "بسيط ونظيف",     "icon": "⬜"},
            {"value": "colorful",  "label": "ملوّن وجذّاب",    "icon": "🌈"},
            {"value": "corporate", "label": "مؤسسي واحترافي", "icon": "💼"},
            {"value": "dark",      "label": "داكن وغامق",     "icon": "🌙"},
        ],
    },
    {
        "question_id": "color",
        "question": "ما نظام الألوان المفضل؟",
        "field_type": "single",
        "options": [
            {"value": "indigo",  "label": "نيلي / بنفسجي",  "icon": "🟣"},
            {"value": "blue",    "label": "أزرق",           "icon": "🔵"},
            {"value": "green",   "label": "أخضر",           "icon": "🟢"},
            {"value": "orange",  "label": "برتقالي / ذهبي", "icon": "🟠"},
            {"value": "red",     "label": "أحمر",           "icon": "🔴"},
            {"value": "neutral", "label": "رمادي محايد",    "icon": "⬛"},
        ],
    },
    {
        "question_id": "sections",
        "question": "ما الأقسام التي تريدها؟ (يمكن اختيار أكثر من خيار)",
        "field_type": "multi",
        "options": [
            {"value": "hero",         "label": "قسم رئيسي (Hero)",  "icon": "🎯"},
            {"value": "features",     "label": "الميزات والمزايا",    "icon": "⭐"},
            {"value": "stats",        "label": "إحصاءات وأرقام",     "icon": "📊"},
            {"value": "pricing",      "label": "الأسعار والباقات",    "icon": "💰"},
            {"value": "testimonials", "label": "آراء العملاء",        "icon": "💬"},
            {"value": "faq",          "label": "الأسئلة الشائعة",    "icon": "❓"},
            {"value": "contact",      "label": "تواصل معنا",          "icon": "📧"},
            {"value": "cta",          "label": "زر الدعوة للعمل",    "icon": "🚀"},
        ],
    },
    {
        "question_id": "direction",
        "question": "ما اتجاه النص؟",
        "field_type": "single",
        "options": [
            {"value": "rtl", "label": "عربي (يمين لليسار)", "icon": "🇸🇦"},
            {"value": "ltr", "label": "إنجليزي (يسار لليمين)", "icon": "🇺🇸"},
            {"value": "both", "label": "ثنائي اللغة", "icon": "🌐"},
        ],
    },
]

_STYLE_LABELS: dict[str, str] = {
    "modern": "عصري وأنيق",
    "minimal": "بسيط ونظيف",
    "colorful": "ملوّن وجذّاب",
    "corporate": "مؤسسي احترافي",
    "dark": "داكن",
}

_COLOR_LABELS: dict[str, str] = {
    "indigo": "النيلي/البنفسجي (indigo/violet)",
    "blue": "الأزرق (blue)",
    "green": "الأخضر (green/emerald)",
    "orange": "البرتقالي/الذهبي (orange/amber)",
    "red": "الأحمر (red/rose)",
    "neutral": "الرمادي المحايد (slate/gray)",
}

_SECTION_LABELS: dict[str, str] = {
    "hero": "قسم Hero رئيسي في الأعلى",
    "features": "قسم الميزات والمزايا",
    "stats": "قسم الإحصاءات والأرقام",
    "pricing": "قسم الأسعار والباقات",
    "testimonials": "قسم آراء العملاء",
    "faq": "قسم الأسئلة الشائعة",
    "contact": "قسم التواصل",
    "cta": "زر الدعوة للعمل (CTA)",
}


async def design_agent(task_id: str, goal: str) -> dict:
    """Run the interactive design pipeline and return html_artifact result."""
    from ..utils.event_bus import Event, bus
    from .html_artifact import html_artifact

    answers: dict[str, Any] = {}

    # Ask each question and collect answers
    for q in _QUESTIONS:
        register(task_id)
        await bus.publish(Event(task_id=task_id, type="agent_question", data=q))
        ans = await wait_answer(task_id, timeout=90.0)
        if ans:
            answers[str(q["question_id"])] = ans.get("value")

    # Build design context from collected answers
    style_key = str(answers.get("style") or "modern")
    color_key = str(answers.get("color") or "indigo")
    direction = str(answers.get("direction") or "rtl")
    sections_raw = answers.get("sections") or ["hero", "features", "cta"]
    sections: list[str] = sections_raw if isinstance(sections_raw, list) else [str(sections_raw)]

    section_desc = "\n".join(
        f"  - {_SECTION_LABELS.get(s, s)}" for s in sections
    )

    is_rtl = direction in ("rtl", "both")
    context = f"""
تفضيلات المستخدم لهذا التصميم:
- أسلوب التصميم: {_STYLE_LABELS.get(style_key, style_key)}
- نظام الألوان الرئيسي: {_COLOR_LABELS.get(color_key, color_key)}
- اتجاه النص: {'RTL (يمين لليسار)' if is_rtl else 'LTR (يسار لليمين)'}
- الأقسام المطلوبة:
{section_desc}

يجب استخدام Tailwind CSS أو CSS مخصص. يجب أن تكون الصفحة مكتملة وقابلة للتشغيل مباشرة في المتصفح.
{'يجب إضافة dir="rtl" و font-family للخط العربي.' if is_rtl else ''}
"""

    result = await html_artifact(goal=goal, context=context)
    return {"content": result.content, "filename": result.filename, "path": result.path}
