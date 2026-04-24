import React, { forwardRef } from 'react';

export const Shimmer = forwardRef<HTMLDivElement, any>(
  ({ children, className, duration, ...props }, ref) => (
    <div ref={ref} className={className} {...props}>
      {children}
    </div>
  )
);
Shimmer.displayName = 'Shimmer';
