import { describe, expect, it } from 'vitest'
import { verdictSentence } from './copy'

describe('verdictSentence', () => {
  it('matches the campaign phrasing pattern from DESIGN_SYSTEM §6', () => {
    expect(verdictSentence('coordinated_paraphrase_campaign', 212, 0.81)).toBe(
      'Likely one coordinated campaign — 212 reworded comments, 81% within 24 hours.',
    )
  })

  it('matches the form letter phrasing pattern', () => {
    expect(verdictSentence('form_letter', 48, 0.3)).toBe('Form letter — 48 near-identical comments.')
  })

  it('matches the organic agreement phrasing exactly (no numbers)', () => {
    expect(verdictSentence('organic_agreement', 9, 0.1)).toBe('Similar views, independently worded.')
  })

  it('matches the insufficient evidence phrasing exactly (no numbers)', () => {
    expect(verdictSentence('insufficient_evidence', 2, 0.0)).toBe(
      'Not enough evidence to call this a campaign.',
    )
  })

  it('rounds the burst percentage rather than truncating', () => {
    expect(verdictSentence('coordinated_paraphrase_campaign', 10, 0.805)).toContain('81%')
  })
})
