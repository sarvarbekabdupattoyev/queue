import { motion, useReducedMotion } from 'motion/react'

/** Word-by-word blur/rise reveal (ReactBits-style BlurText). */
export function BlurText({
  text,
  delay = 0,
  step = 0.055,
  className,
}: {
  text: string
  delay?: number
  step?: number
  className?: string
}) {
  const reduced = useReducedMotion()
  const words = text.split(' ')
  if (reduced) return <span className={className}>{text}</span>
  // className (e.g. grad-text with background-clip) is applied per word: the
  // animated spans are separate compositing layers, which would break a
  // text-clipped background painted on the parent.
  return (
    <span aria-label={text}>
      {words.map((word, i) => (
        <span key={`${word}-${i}`} aria-hidden="true">
          <motion.span
            className={className}
            style={{ display: 'inline-block', willChange: 'transform, filter' }}
            initial={{ opacity: 0, y: 18, filter: 'blur(10px)' }}
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            transition={{ duration: 0.55, delay: delay + i * step, ease: [0.21, 0.6, 0.35, 1] }}
          >
            {word}
          </motion.span>
          {i < words.length - 1 ? ' ' : ''}
        </span>
      ))}
    </span>
  )
}
