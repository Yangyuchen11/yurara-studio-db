// frontend/src/components/ui/FormField.tsx
import React from 'react';

interface FormFieldProps {
  label: string;
  required?: boolean;
  helper?: string;
  children: React.ReactNode;
  className?: string;
}

export const FormField: React.FC<FormFieldProps> = ({
  label,
  required = false,
  helper,
  children,
  className = '',
}) => {
  return (
    <div className={`space-y-1.5 ${className}`}>
      <label className="block text-xs font-medium text-slate-300">
        {label}
        {required && <span className="text-rose-400 font-bold ml-1">*</span>}
      </label>
      {children}
      {helper && <p className="text-[11px] text-slate-400">{helper}</p>}
    </div>
  );
};
