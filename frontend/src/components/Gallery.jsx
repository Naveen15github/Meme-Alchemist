import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import Lightbox from './Lightbox.jsx'

export default function Gallery({ memes, loading, ownedIds, onDelete }) {
  const [selected, setSelected] = useState(null)
  const [confirmingId, setConfirmingId] = useState(null)
  const [deletingId, setDeletingId] = useState(null)

  const owns = (id) => Boolean(ownedIds?.has(id))

  const confirmDelete = async (meme) => {
    setDeletingId(meme.id)
    try {
      await onDelete(meme)
    } finally {
      setDeletingId(null)
      setConfirmingId(null)
    }
  }

  if (loading) {
    return (
      <div className="columns-2 gap-4 sm:columns-3" aria-busy="true" aria-label="Loading gallery">
        {Array.from({ length: 6 }).map((_, index) => (
          <div
            key={index}
            style={{ height: `${140 + (index % 3) * 60}px` }}
            className="mb-4 break-inside-avoid rounded-2xl bg-gradient-to-r from-white/5 via-white/10 to-white/5
                       bg-[length:200%_100%] animate-shimmer"
          />
        ))}
      </div>
    )
  }

  if (!memes.length) {
    return (
      <p className="py-10 text-center text-sm text-slate-500">
        No memes yet. Be the first to brew one. 🧪
      </p>
    )
  }

  return (
    <>
      {/* CSS columns give a real masonry layout without a layout library. */}
      <div className="columns-2 gap-4 sm:columns-3">
        <AnimatePresence initial={false}>
          {memes.map((meme, index) => (
            <motion.div
              key={meme.id}
              layout
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.85, filter: 'blur(4px)' }}
              transition={{ delay: Math.min(index * 0.05, 0.6), duration: 0.4 }}
              className="group relative mb-4 block w-full break-inside-avoid overflow-hidden
                         rounded-2xl border border-white/10 bg-white/[0.03]"
            >
              <button
                type="button"
                onClick={() => setSelected(meme)}
                className="block w-full focus:outline-none focus-visible:ring-2 focus-visible:ring-fuchsia-400"
                aria-label={meme.caption ? `View meme: ${meme.caption}` : 'View meme'}
              >
                <img
                  src={meme.imageUrl}
                  alt={meme.caption || 'A generated meme'}
                  loading="lazy"
                  className="w-full transition-transform duration-500 group-hover:scale-[1.06]"
                />
                <div
                  className="pointer-events-none absolute inset-0 flex items-end bg-gradient-to-t
                             from-black/85 via-black/20 to-transparent p-3 opacity-0
                             transition-opacity duration-300 group-hover:opacity-100"
                >
                  <p className="line-clamp-2 text-left text-xs font-medium text-white">{meme.caption}</p>
                </div>
              </button>

              {/* Only memes this browser created carry a delete token. */}
              {owns(meme.id) && (
                <button
                  type="button"
                  onClick={() => setConfirmingId(meme.id)}
                  aria-label={`Delete meme: ${meme.caption || meme.id}`}
                  className="absolute right-2 top-2 grid h-9 w-9 place-items-center rounded-full
                             bg-black/60 text-sm text-white/80 opacity-0 backdrop-blur
                             transition-all duration-200 hover:bg-rose-500/80 hover:text-white
                             focus:opacity-100 focus:outline-none focus-visible:ring-2
                             focus-visible:ring-rose-400 group-hover:opacity-100"
                >
                  🗑
                </button>
              )}

              {confirmingId === meme.id && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  role="alertdialog"
                  aria-label="Confirm deleting this meme"
                  className="absolute inset-0 grid place-items-center gap-3 bg-black/85 p-4 backdrop-blur-sm"
                >
                  <p className="text-center text-xs font-medium text-white">Delete this meme?</p>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => confirmDelete(meme)}
                      disabled={deletingId === meme.id}
                      className="rounded-lg bg-rose-500 px-3 py-1.5 text-xs font-semibold text-white
                                 hover:bg-rose-400 disabled:opacity-60"
                    >
                      {deletingId === meme.id ? 'Deleting…' : 'Delete'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmingId(null)}
                      className="rounded-lg bg-white/10 px-3 py-1.5 text-xs font-semibold text-slate-200
                                 hover:bg-white/20"
                    >
                      Cancel
                    </button>
                  </div>
                </motion.div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      <Lightbox meme={selected} onClose={() => setSelected(null)} />
    </>
  )
}
