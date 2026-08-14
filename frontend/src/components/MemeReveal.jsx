import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'

/** Small burst of sparks on reveal. Decorative, and cheap. */
function Sparkles() {
  const sparks = Array.from({ length: 14 })
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden rounded-2xl">
      {sparks.map((_, index) => {
        const angle = (index / sparks.length) * Math.PI * 2
        return (
          <motion.span
            key={index}
            className="absolute left-1/2 top-1/2 h-1.5 w-1.5 rounded-full bg-amber-300"
            initial={{ opacity: 1, x: 0, y: 0, scale: 1 }}
            animate={{
              opacity: 0,
              x: Math.cos(angle) * (110 + Math.random() * 90),
              y: Math.sin(angle) * (110 + Math.random() * 90),
              scale: 0,
            }}
            transition={{ duration: 0.9 + Math.random() * 0.4, ease: 'easeOut', delay: 0.15 }}
          />
        )
      })}
    </div>
  )
}

function CopyButton({ url }) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) return undefined
    const timer = setTimeout(() => setCopied(false), 1800)
    return () => clearTimeout(timer)
  }, [copied])

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
    } catch {
      // Clipboard can be blocked (insecure context, permissions). Fall back to
      // a selectable prompt rather than failing silently.
      window.prompt('Copy this link:', url)
    }
  }

  return (
    <motion.button
      type="button"
      onClick={copy}
      whileTap={{ scale: 0.95 }}
      className="btn-ghost"
      aria-label="Copy a shareable link to this meme"
    >
      <motion.span key={copied ? 'yes' : 'no'} initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}>
        {copied ? '✓ Link copied' : '🔗 Copy link'}
      </motion.span>
    </motion.button>
  )
}

export default function MemeReveal({ meme, onReset }) {
  const [downloading, setDownloading] = useState(false)

  const download = async () => {
    setDownloading(true)
    try {
      // Fetch as a blob so the file saves instead of navigating to it.
      const response = await fetch(meme.imageUrl)
      const blob = await response.blob()
      const href = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = href
      link.download = `meme-alchemist-${meme.id}.jpg`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(href)
    } catch {
      window.open(meme.imageUrl, '_blank', 'noopener')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <motion.section
      initial={{ opacity: 0, scale: 0.9, y: 24 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 190, damping: 20 }}
      className="w-full"
      aria-label="Your finished meme"
    >
      <div className="glass relative overflow-hidden rounded-3xl p-4 sm:p-6">
        <Sparkles />

        <div className="relative overflow-hidden rounded-2xl bg-black/40">
          <motion.img
            src={meme.imageUrl}
            alt={meme.caption ? `Meme: ${meme.caption}` : 'Your generated meme'}
            className="mx-auto max-h-[62vh] w-auto max-w-full object-contain"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.45, delay: 0.1 }}
          />
        </div>

        {meme.labels?.length > 0 && (
          <div className="mt-5 flex flex-wrap items-center gap-2">
            <span className="text-xs uppercase tracking-wider text-slate-500">Rekognition saw</span>
            {meme.labels.slice(0, 6).map((label) => (
              <span
                key={label}
                className="rounded-full bg-white/[0.06] px-3 py-1 text-xs font-medium text-slate-300"
              >
                {label}
              </span>
            ))}
          </div>
        )}

        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <motion.button
            type="button"
            onClick={download}
            whileTap={{ scale: 0.95 }}
            disabled={downloading}
            className="btn-primary"
          >
            {downloading ? 'Saving…' : '⬇ Download'}
          </motion.button>

          <CopyButton url={meme.imageUrl} />

          <motion.button type="button" onClick={onReset} whileTap={{ scale: 0.95 }} className="btn-ghost">
            ✨ Make another
          </motion.button>
        </div>

        {meme.captionSource === 'fallback' && (
          <p className="mt-5 text-center text-xs text-slate-500">
            Caption written by the built-in joke library — the model was unavailable, so the
            alchemist improvised.
          </p>
        )}
      </div>
    </motion.section>
  )
}
