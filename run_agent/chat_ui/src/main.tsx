import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'


const vuePlaceholder = document.createElement('div');
vuePlaceholder.id = 'vueApp';
document.body.prepend(vuePlaceholder);


createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
)
