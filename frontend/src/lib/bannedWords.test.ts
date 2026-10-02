/// <reference types="node" />
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { BANNED_WORDS } from './copy'

// Files that may legitimately *mention* the banned words (defining the rule itself),
// as opposed to using them as product copy.
const EXCLUDED_FILES = new Set(['copy.ts', 'copy.test.ts', 'bannedWords.test.ts'])

function collectSourceFiles(dir: string): string[] {
  const files: string[] = []
  for (const entry of readdirSync(dir)) {
    const fullPath = join(dir, entry)
    const info = statSync(fullPath)
    if (info.isDirectory()) {
      files.push(...collectSourceFiles(fullPath))
    } else if (/\.(ts|tsx)$/.test(entry) && !EXCLUDED_FILES.has(entry)) {
      files.push(fullPath)
    }
  }
  return files
}

describe('banned vocabulary (DESIGN_SYSTEM §6)', () => {
  const srcDir = join(__dirname, '..')
  const files = collectSourceFiles(srcDir)

  it('scanned at least the expected number of source files', () => {
    expect(files.length).toBeGreaterThan(10)
  })

  for (const word of BANNED_WORDS) {
    it(`never appears as product copy: "${word}"`, () => {
      const pattern = new RegExp(`\\b${word}\\b`, 'i')
      const offenders = files.filter((file) => pattern.test(readFileSync(file, 'utf-8')))
      expect(offenders).toEqual([])
    })
  }

  it('never claims "AI detected"', () => {
    const pattern = /AI detected/i
    const offenders = files.filter((file) => pattern.test(readFileSync(file, 'utf-8')))
    expect(offenders).toEqual([])
  })
})
