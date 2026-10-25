import { minutes } from "../lib/format";
import type { LibraryItem } from "../lib/types";

interface Props {
  items: LibraryItem[];
  onOpen(videoId: string): void;
  onForget(videoId: string): void;
}

export function Library({ items, onOpen, onForget }: Props) {
  if (!items.length) return null;
  return (
    <section className="library" aria-label="Your lectures">
      <h3>Your lectures</h3>
      <div className="library-grid">
        {items.map((item) => (
          <article key={item.video_id} className="lecture-card">
            <button className="lecture-open" onClick={() => onOpen(item.video_id)}>
              <span className="lecture-thumb">
                <img
                  src={`https://i.ytimg.com/vi/${item.video_id}/mqdefault.jpg`}
                  alt=""
                  loading="lazy"
                  // Offline, keep the plain placeholder instead of a broken-image icon.
                  onError={(e) => (e.currentTarget.style.visibility = "hidden")}
                />
              </span>
              <span className="lecture-title">{item.title}</span>
              <span className="lecture-meta">
                {minutes(item.duration)} · {item.engine === "ollama" ? "Local AI" : "Offline estimate"}
              </span>
            </button>
            <button
              className="lecture-forget"
              aria-label={`Remove ${item.title}`}
              title="Remove from library"
              onClick={() => onForget(item.video_id)}
            >
              ×
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
