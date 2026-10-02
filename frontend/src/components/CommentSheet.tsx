import { displaySubmitter, useHideNames } from '../context/HideNamesContext'

interface CommentSheetProps {
  text: string
  submitterLabel: string
  submitterHash: string
  postedAt: string | null
  lines?: number
  bordered?: boolean
}

export function CommentSheet({
  text,
  submitterLabel,
  submitterHash,
  postedAt,
  lines,
  bordered = true,
}: CommentSheetProps) {
  const { hideNames } = useHideNames()
  const name = displaySubmitter(submitterLabel, hideNames, submitterHash)

  return (
    <div
      className={`rounded-sheet bg-paper p-4 shadow-sheet ${bordered ? 'border border-rule' : ''}`}
    >
      <p
        className="font-serif text-base leading-[1.65] text-ink"
        style={
          lines
            ? {
                display: '-webkit-box',
                WebkitLineClamp: lines,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
              }
            : { maxWidth: '72ch' }
        }
      >
        {text}
      </p>
      <p className="mt-2 text-xs text-ink-soft">
        {name}
        {postedAt ? ` · ${new Date(postedAt).toLocaleString()}` : ''}
      </p>
    </div>
  )
}
