// frontend/src/components/ui/StatCard.tsx
import React from 'react';
import type { LucideIcon } from 'lucide-react';

interface StatCardProps {
  label: string;
  value: string | number;
  unit?: string;
  icon?: LucideIcon;
  colorScheme?: 'violet' | 'slate' | 'emerald' | 'rose' | 'blue' | 'amber' | 'indigo';
  borderLeft?: boolean;
}

const colorMap = {
  violet: {
    icon: 'text-violet-400',
    border: 'border-l-violet-500',
    bg: 'bg-violet-500/10',
    text: 'text-violet-300',
  },
  slate: {
    icon: 'text-slate-400',
    border: 'border-l-slate-500',
    bg: 'bg-slate-500/10',
    text: 'text-slate-200',
  },
  emerald: {
    icon: 'text-emerald-400',
    border: 'border-l-emerald-500',
    bg: 'bg-emerald-500/10',
    text: 'text-emerald-300',
  },
  rose: {
    icon: 'text-rose-400',
    border: 'border-l-rose-500',
    bg: 'bg-rose-500/10',
    text: 'text-rose-300',
  },
  blue: {
    icon: 'text-blue-400',
    border: 'border-l-blue-500',
    bg: 'bg-blue-500/10',
    text: 'text-blue-300',
  },
  amber: {
    icon: 'text-amber-400',
    border: 'border-l-amber-500',
    bg: 'bg-amber-500/10',
    text: 'text-amber-300',
  },
  indigo: {
    icon: 'text-indigo-400',
    border: 'border-l-indigo-500',
    bg: 'bg-indigo-500/10',
    text: 'text-indigo-300',
  },
};

export const StatCard: React.FC<StatCardProps> = ({
  label,
  value,
  unit,
  icon: Icon,
  colorScheme = 'violet',
  borderLeft = false,
}) => {
  const styles = colorMap[colorScheme] || colorMap.violet;

  return (
    <div
      className={`p-4 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] shadow-sm hover:shadow-md transition-all duration-200 ${
        borderLeft ? `border-l-4 ${styles.border}` : ''
      }`}
    >
      <div className="flex items-center gap-1.5 mb-2">
        {Icon && <Icon className={`w-4 h-4 ${styles.icon}`} />}
        <span className="text-xs font-medium text-slate-400">{label}</span>
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-2xl font-bold font-mono text-slate-100 tracking-tight">
          {value}
        </span>
        {unit && <span className="text-xs text-slate-400">{unit}</span>}
      </div>
    </div>
  );
};
