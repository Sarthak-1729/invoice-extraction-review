import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'

// Tests never use the network: every API call goes through a fake api
// object. Real fetch and XMLHttpRequest throw if anything tries.
beforeEach(() => {
  vi.stubGlobal('fetch', () => {
    throw new Error('Network is blocked in tests (use the fake api).')
  })
  vi.stubGlobal(
    'XMLHttpRequest',
    class {
      constructor() {
        throw new Error('Network is blocked in tests (use the fake api).')
      }
    },
  )
  window.location.hash = ''
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

// index.html sets lang="en"; jsdom's empty document does not.
document.documentElement.lang = 'en'

// jsdom does not implement scrolling.
Element.prototype.scrollIntoView = function scrollIntoView() {}
