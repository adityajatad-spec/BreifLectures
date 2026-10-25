import { CUTS, type CutId } from "../lib/cuts";
import { minutes } from "../lib/format";

interface Props {
  value: CutId;
  onChange(id: CutId): void;
  durations: Record<CutId, number>;
  target: number;
  targetMax: number;
  onTarget(seconds: number): void;
}

export function CutPicker({ value, onChange, durations, target, targetMax, onTarget }: Props) {
  return (
    <div className="cuts">
      <div className="cut-grid" role="radiogroup" aria-label="Choose a cut">
        {CUTS.map((cut) => (
          <button
            key={cut.id}
            role="radio"
            aria-checked={value === cut.id}
            className={`cut ${value === cut.id ? "active" : ""}`}
            onClick={() => onChange(cut.id)}
          >
            <span className="cut-name">{cut.name}</span>
            <span className="cut-length">{minutes(durations[cut.id])}</span>
            <span className="cut-blurb">{cut.blurb}</span>
          </button>
        ))}
      </div>
      {value === "custom" && (
        <label className="slider">
          Target length: <strong>{minutes(target)}</strong>
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
    </div>
  );
}
