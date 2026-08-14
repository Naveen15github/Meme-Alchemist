import { useState } from 'react'
import { motion } from 'framer-motion'
import Lightbox from './Lightbox.jsx'

export default function Gallery({ memes, loading }) {
  const [selected, setSelected] = useState(null)

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
        {memes.map((meme, index) => (
          <motion.button
            key={meme.id}
            type="button"
            onClick={() => setSelected(meme)}
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(index * 0.05, 0.6), duration: 0.4 }}
            whileHover={{ y: -4 }}
            className="group relative mb-4 block w-full break-inside-avoid overflow-hidden rounded-2xl
                       border border-white/10 bg-white/[0.03] focus:outline-none
                       focus-visible:ring-2 focus-visible:ring-fuchsia-400"
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
          </motion.button>
        ))}
      </div>

      <Lightbox meme={selected} onClose={() => setSelected(null)} />
    </>
  )
}
