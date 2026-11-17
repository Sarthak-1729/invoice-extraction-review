// A button that can be "unavailable" without the `disabled` attribute.
// Disabling the focused button would drop keyboard focus to <body>; with
// aria-disabled the button keeps focus, is announced as unavailable, and
// ignores clicks (including form submission).
export default function Button({ unavailable = false, onClick, className = 'button', type = 'button', ...rest }) {
  function handleClick(event) {
    if (unavailable) {
      event.preventDefault()
      return
    }
    onClick?.(event)
  }
  return (
    <button
      type={type}
      className={className}
      aria-disabled={unavailable ? 'true' : undefined}
      onClick={handleClick}
      {...rest}
    />
  )
}
