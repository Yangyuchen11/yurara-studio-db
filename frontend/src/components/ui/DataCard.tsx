// frontend/src/components/ui/DataCard.tsx
import React from 'react';

interface DataCardProps {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export const DataCard: React.FC<DataCardProps> = ({ title, action, children, className = '' }) => {
  return (
    <div className={`p-5 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] space-y-4 shadow-sm hover:shadow-md transition-shadow ${className}`}>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-slate-100 tracking-tight">{title}</h3>
        {action && <div>{action}</div>}
      </div>
      <div className="border-b border-[#2A3447]" />
      <div>{children}</div>
    </div>
  );
};
