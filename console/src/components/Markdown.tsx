import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { useMemo, type MouseEvent } from 'react';

marked.setOptions({ gfm: true, breaks: false });

// Wiki links ([[accounts/x]]) become source chips that open the page.
const WIKI = /\[\[([a-z0-9/_.-]+)\]\]/gi;

export function Markdown({ text, streaming, onSource }: { text: string; streaming?: boolean; onSource: (path: string) => void }) {
  const html = useMemo(() => {
    const withLinks = text.replace(WIKI, (_, p) => `<a href="#src=wiki/${p}.md" data-src="wiki/${p}.md">${p.split('/').pop()}</a>`);
    return DOMPurify.sanitize(marked.parse(withLinks, { async: false }) as string, { ADD_ATTR: ['data-src'] });
  }, [text]);

  const click = (e: MouseEvent<HTMLDivElement>) => {
    const a = (e.target as HTMLElement).closest('a');
    if (!a) return;
    const src = a.getAttribute('data-src') ?? (/^(wiki|raw|knowledge|log|reps)\//.test(a.getAttribute('href') ?? '') ? a.getAttribute('href') : null);
    if (src) { e.preventDefault(); onSource(src); return; }
    // Model output links open outside the console, never in it.
    a.setAttribute('target', '_blank');
    a.setAttribute('rel', 'noopener noreferrer');
  };

  return <div className={`md${streaming ? ' caret' : ''}`} onClick={click} dangerouslySetInnerHTML={{ __html: html }} />;
}
