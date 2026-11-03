import { CUTS, type CutId } from "../lib/cuts";
import { minutes } from "../lib/format";
import { Icon, type IconName } from "./Icon";

const ICONS: Record<CutId, IconName> = {
  full: "film",
  "no-filler": "scissors",
  "key-moments": "zap",
  custom: "sliders",
};

interface Props {
  value: CutId;
  onChange(id: CutId): void;
  durations: Record<CutId, number>;
  full: number;
  target: number;
  targetMax: number;
  onTarget(seconds: number): void;
}

export function CutPicker({ value, onChange, durations, full, target, targetMax, onTarget }: Props) {
  return (
    <section className="glass cuts">
      <h3>
        <Icon name="scissors" size={16} /> Choose your cut
      </h3>
      <div className="cut-grid" role="radiogroup" aria-label="Choose a cut">
        {CUTS.map((cut) => {
          const share = full ? Math.min(100, (durations[cut.id] / full) * 100) : 0;
          return (
            <button
              key={cut.id}
              role="radio"
              aria-checked={value === cut.id}
              className={`cut ${value === cut.id ? "active" : ""}`}
              onClick={() => onChange(cut.id)}
            >
              <span className="cut-icon">
                <Icon name={ICONS[cut.id]} size={17} />
              </span>
              <span className="cut-text">
                <span className="cut-name">{cut.name}</span>
                <span className="cut-blurb">{cut.blurb}</span>
              </span>
              <span className="cut-length">{minutes(durations[cut.id])}</span>
              <span className="cut-share" aria-hidden>
                <span style={{ width: `${share}%` }} />
              </span>
            </button>
          );
        })}
      </div>
      {value === "custom" && (
        <label className="slider">
          <span>
            Target length <strong>{minutes(target)}</strong>
          </span>
          <input
            type="range"
            min={60}
            max={Math.max(60, Math.round(targetMax))}
            step={30}
            value={target}
            onChange={(e) => onTarget(Number(e.target.value))}
          />
        </label>
      )}
    </section>
  );
}
