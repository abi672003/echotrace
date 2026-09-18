interface Option {
  value: string;
  label: string;
}

interface Props {
  label: string;
  value: string;
  options: Option[];
  onChange: (value: string) => void;
}

/** A themed native <select> — accessible and reliable by default, styled
 * to match the case-board aesthetic rather than reimplemented as a custom
 * listbox. */
export default function Select({ label, value, options, onChange }: Props) {
  return (
    <label className="field-select">
      <span className="field-select-label mono">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
