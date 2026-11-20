/**
 * Detects Vietnamese text by letters only Vietnamese uses: ă â đ ê ô ơ ư and the stacked
 * tone-mark range U+1EA0–U+1EF9 (ạ ả ấ ầ … ỹ). Plain accented letters shared with French
 * or Spanish (é, à) are not enough on their own. Mirrors backend clouddocs/lang.py (UI-06).
 */
const VIETNAMESE = /[ăâđêôơưĂÂĐÊÔƠƯẠ-ỹ]/u;

export function isVietnamese(text: string): boolean {
  return VIETNAMESE.test(text.normalize("NFC"));
}

export interface Strings {
  noSourceNote: string;
  /** Same wording as the backend's decline (clouddocs/lang.py), used by the mock API. */
  noEvidenceAnswer: string;
}

export function stringsFor(question: string): Strings {
  return isVietnamese(question)
    ? {
        noSourceNote: "Không có nguồn nào trong tài liệu của bạn cho câu trả lời này.",
        noEvidenceAnswer: "Tôi không tìm thấy thông tin liên quan trong tài liệu của bạn để trả lời câu hỏi này.",
      }
    : {
        noSourceNote: "No source in your documents supports an answer to this question.",
        noEvidenceAnswer: "I could not find relevant information in your documents to answer this question.",
      };
}
