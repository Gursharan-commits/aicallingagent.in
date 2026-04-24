import React, { forwardRef } from 'react';
import { cn } from '@/lib/utils';

export const Conversation = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ children, className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col gap-4", className)} {...props}>
      {children}
    </div>
  )
);
Conversation.displayName = 'Conversation';

export const ConversationContent = ({ children, className }: { children: React.ReactNode, className?: string }) => (
  <div className={cn("flex-1 overflow-y-auto", className)}>{children}</div>
);

export const ConversationScrollButton = () => null;
