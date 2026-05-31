import React from 'react';

const PRESET_COLORS = [
  '#EF4444', '#F97316', '#EAB308', '#22C55E',
  '#10B981', '#14B8A6', '#3B82F6', '#6366F1',
  '#8B5CF6', '#A855F7', '#EC4899', '#F43F5E',
  '#64748B', '#78716C', '#0EA5E9', '#84CC16',
];

interface ColorPickerProps {
  value: string;
  onChange: (color: string) => void;
}

const ColorPicker: React.FC<ColorPickerProps> = ({ value, onChange }) => {
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-8 gap-1.5">
        {PRESET_COLORS.map(color => (
          <button
            key={color}
            type="button"
            onClick={() => onChange(color)}
            className="w-7 h-7 rounded-full transition-transform hover:scale-110 focus:outline-none"
            style={{ backgroundColor: color }}
            title={color}
          >
            {value === color && (
              <span className="flex items-center justify-center w-full h-full">
                <svg className="w-3.5 h-3.5 text-white drop-shadow" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </span>
            )}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <input
          type="color"
          value={value}
          onChange={e => onChange(e.target.value)}
          className="w-8 h-8 rounded cursor-pointer border-0 bg-transparent"
          title="カスタムカラー"
        />
        <span className="text-xs text-gray-500 dark:text-gray-400">カスタムカラー</span>
        <span className="text-xs font-mono text-gray-600 dark:text-gray-300">{value}</span>
      </div>
    </div>
  );
};

export default ColorPicker;
