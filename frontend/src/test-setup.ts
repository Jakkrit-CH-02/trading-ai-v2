import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// vitest runs with globals: false, so RTL's automatic cleanup is not registered.
afterEach(cleanup)
