import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

const storage = {}

Object.defineProperty(window, 'localStorage', {
  value: {
    getItem(key) {
      return key in storage ? storage[key] : null
    },
    setItem(key, value) {
      storage[key] = String(value)
    },
    removeItem(key) {
      delete storage[key]
    },
    clear() {
      Object.keys(storage).forEach((key) => delete storage[key])
    },
  },
  configurable: true,
})

afterEach(() => {
  cleanup()
})
