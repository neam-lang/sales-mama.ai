import { useEffect, useRef, useState } from 'react';

export function SourceDrawer({ path, onClose }: { path: string; onClose: () => void }) {
  const [state, setState] = useState<{ text?: string; truncated?: boolean; error?: string }>({});
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let live = true;
    setState({});
    fetch(`/api/source?path=${encodeURIComponent(path)}`)
      .then(async r => (r.ok ? r.json() : Promise.reject(await r.text())))
      .then(d => live && setState({ text: d.text, truncated: d.truncated }))
      .catch(e => live && setState({ error: String(e) }));
    return () => { live = false; };
  }, [path]);

  useEffect(() => {
    closeRef.current?.focus();
    const key = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [onClose]);

  return (
    <div className="drawer-bg" onClick={onClose}>
      <div className="drawer" role="dialog" aria-modal="true" aria-label={`Source ${path}`} onClick={e => e.stopPropagation()}>
        <header><span>{path}</span><button ref={closeRef} type="button" className="ghost" onClick={onClose}>Close</button></header>
        <pre>{state.error ?? state.text ?? 'Loading…'}{state.truncated ? '\n\n… (truncated)' : ''}</pre>
      </div>
    </div>
  );
}
