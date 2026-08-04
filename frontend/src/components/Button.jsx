const VARIANTS = {
  primary: 'bg-primary text-white shadow-xs hover:bg-primary-hover active:bg-primary-active',
  success: 'bg-success text-white shadow-xs hover:bg-success-hover',
  danger: 'bg-error text-white shadow-xs hover:bg-error-hover',
  secondary: 'bg-white border border-gray-300 text-navy hover:bg-surface-sunken hover:border-gray-400',
  ghost: 'text-text-secondary hover:bg-surface-sunken hover:text-navy',
}

// sm: dense admin list/toggle contexts (~30px). md: default (~37px).
// lg: touch target for trainer-facing primary actions, e.g. Mark Attendance (~44px).
const SIZES = {
  sm: 'text-xs px-3 py-1.5 gap-1.5 rounded-md',
  md: 'text-sm px-4 py-2 gap-2 rounded-lg',
  lg: 'text-sm px-5 py-3 gap-2 rounded-lg',
}

/**
 * Shared button. variant: primary (default action) / success (positive
 * confirm, e.g. "Save") / danger (destructive) / secondary (outline,
 * cancel/secondary action) / ghost (text-only, low-emphasis action).
 */
export function Button({ variant = 'primary', size = 'md', className = '', type = 'button', ...props }) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center font-medium transition-colors duration-150 ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:opacity-45 disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...props}
    />
  )
}
