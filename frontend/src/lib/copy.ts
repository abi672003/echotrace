import type { ClusterType } from '../api/types'

/** Verdict phrasing, verbatim pattern from DESIGN_SYSTEM §6. */
export function verdictSentence(type: ClusterType, size: number, burst24h: number): string {
  switch (type) {
    case 'coordinated_paraphrase_campaign':
      return `Likely one coordinated campaign — ${size} reworded comments, ${Math.round(burst24h * 100)}% within 24 hours.`
    case 'form_letter':
      return `Form letter — ${size} near-identical comments.`
    case 'organic_agreement':
      return 'Similar views, independently worded.'
    case 'insufficient_evidence':
      return 'Not enough evidence to call this a campaign.'
  }
}

/** Vocabulary the product must never use (DESIGN_SYSTEM §6) — the product cannot
 * verify identities and must not imply it can. Checked by the Task 4.13 copy audit. */
export const BANNED_WORDS = ['fake', 'bot', 'sockpuppet', 'astroturf', 'fraud', 'fraudulent']
