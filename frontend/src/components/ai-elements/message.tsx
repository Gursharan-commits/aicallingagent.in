import React from 'react';
import { cn } from '@/lib/utils';

export const Message = ({ children, title, from, className }: any) => (
  <div className={cn("flex flex-col mb-4", from === 'user' ? "items-end" : "items-start", className)}>
    {title && <span className="text-[10px] text-on-surface-variant mb-1">{title}</span>}
    {children}
  </div>
);

export const MessageContent = ({ children, className }: any) => (
  <div className={cn("max-w-[80%] rounded-lg p-3", className)}>{children}</div>
);

export const MessageResponse = ({ children }: any) => (
  <div className="text-sm">{children}</div>
);
