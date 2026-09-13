export function FormError({ errors }: { errors?: string[] }) {
  if (!errors || errors.length === 0) return null
  return <div className="field-errors">{errors.join(' ')}</div>
}
