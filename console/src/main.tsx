import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './styles/tokens.css';
import './styles.css';
import './a2ui/a2ui.css';
import './styles/shell.css';
import './styles/chat.css';
import './styles/calendar.css';
import './styles/canvas.css';
import './styles/voice.css';

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
