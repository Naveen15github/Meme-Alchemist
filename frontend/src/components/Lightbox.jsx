import { useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

export default function Lightbox({ meme, onClose }) {
  useEffect(() => {
    if (!meme) return undefined
    const onKey = (event) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [meme, onClose])

  return (
    <AnimatePresence>
      {meme && (
        <motion.div
          role="dialog"
          aria-modal="true"
          aria-label="Meme preview"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 z-50 grid place-items-center bg-black/80 p-4 backdrop-blur-md"
        >
          <motion.div
            initial={{ scale: 0.92, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.92, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 240, damping: 24 }}
            onClick={(event) => event.stopPropagation()}
            className="relative max-w-3xl"
          >
            <img
              src={meme.imageUrl}
              alt={meme.caption || 'Meme'}
              className="max-h-[80vh] w-auto max-w-full rounded-2xl shadow-2xl"
            />
            <button
              type="button"
              onClick={onClose}
              aria-label="Close preview"
              className="absolute -right-3 -top-3 grid h-10 w-10 place-items-center rounded-full
                         bg-white/10 text-lg text-white backdrop-blur hover:bg-white/20"
            >
              ✕
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
