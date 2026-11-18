import axe from 'axe-core'

// axe-core run directly on the rendered document. jsdom has no layout or
// computed colors, so `color-contrast` cannot be checked here (it is checked
// in a real browser; ratios are recorded in styles.css). jsdom cannot run
// axe inside the PDF frame either.
export async function axeViolations() {
  const results = await axe.run(document, {
    runOnly: {
      type: 'tag',
      values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'],
    },
    rules: { 'color-contrast': { enabled: false } },
    iframes: false, // jsdom cannot message frames; the PDF frame's title is still checked
  })
  return results.violations.map(
    (v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`,
  )
}
