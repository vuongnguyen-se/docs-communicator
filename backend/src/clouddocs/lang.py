"""Language helpers (UI-06). Mirrors frontend/src/lang.ts.

Vietnamese is detected by letters only Vietnamese uses: ă â đ ê ô ơ ư and the stacked
tone-mark range U+1EA0-U+1EF9. Accents shared with French or Spanish (é, à) don't count.
"""

from __future__ import annotations

import re
import unicodedata

_VIETNAMESE = re.compile(r"[ăâđêôơưĂÂĐÊÔƠƯẠ-ỹ]")

NO_EVIDENCE = {
    "en": "I could not find relevant information in your documents to answer this question.",
    "vi": "Tôi không tìm thấy thông tin liên quan trong tài liệu của bạn để trả lời câu hỏi này.",
}


def is_vietnamese(text: str) -> bool:
    return bool(_VIETNAMESE.search(unicodedata.normalize("NFC", text)))


def no_evidence_message(question: str) -> str:
    return NO_EVIDENCE["vi" if is_vietnamese(question) else "en"]
