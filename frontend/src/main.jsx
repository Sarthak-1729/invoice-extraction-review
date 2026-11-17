import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import { createApi } from './api.js'
import './styles.css'

const api = createApi(import.meta.env.VITE_API_URL || 'http://localhost:8000')

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App api={api} />
  </StrictMode>,
)
