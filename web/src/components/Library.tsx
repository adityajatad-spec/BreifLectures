import { minutes } from "../lib/format";
import type { LibraryItem } from "../lib/types";
import { Icon } from "./Icon";

interface Props {
  items: LibraryItem[];
  onOpen(videoId: string): void;
  onForget(videoId: string): void;
}

export function Library({ items, onOpen, onForget }: Props) {
  if (!items.length) return null;
  return (
    <section className="library" aria-label="Your lectures">
      <div className="section-head">
        <h3>Your lectures</h3>
        <span className="count">{items.length}</span>
      </div>
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
                <span className="thumb-play" aria-hidden>
                  <Icon name="play" size={18} />
                </span>
                <span className="thumb-duration">{minutes(item.duration)}</span>
              </span>
              <span className="lecture-body">
                <span className="lecture-title">{item.title}</span>
                <span className={`chip chip-small ${item.engine === "ollama" ? "chip-ai" : ""}`}>
                  <Icon name={item.engine === "ollama" ? "cpu" : "zap"} size={12} />
                  {item.engine === "ollama" ? "Local AI" : "Offline estimate"}
                </span>
              </span>
            </button>
            <button
              className="lecture-forget"
              aria-label={`Remove ${item.title}`}
              title="Remove from library"
              onClick={() => onForget(item.video_id)}
            >
              <Icon name="x" size={14} />
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
