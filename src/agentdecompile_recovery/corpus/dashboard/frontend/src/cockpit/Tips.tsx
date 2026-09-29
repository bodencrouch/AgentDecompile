import { useEffect, useRef, useState, type RefObject } from 'react';

/**
 * One tooltip for every [data-tip] element under `root`, on hover and on
 * keyboard focus. Text only; explanations live here instead of on screen.
 */
export function TipLayer({ root }: { root: RefObject<HTMLElement | null> }) {
  const [tip, setTip] = useState<{ text: string; x: number; y: number; below: boolean } | null>(null);
  const current = useRef<Element | null>(null);

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const show = (target: EventTarget | null) => {
      const node = target instanceof Element ? target.closest('[data-tip]') : null;
      if (!node || !el.contains(node)) return hide();
      if (node === current.current) return;
      current.current = node;
      const text = node.getAttribute('data-tip') || '';
      if (!text) return hide();
      const r = node.getBoundingClientRect();
      const below = r.top < 80;
      setTip({ text, x: Math.min(window.innerWidth - 16, Math.max(16, r.left + r.width / 2)), y: below ? r.bottom + 8 : r.top - 8, below });
    };
    const hide = () => {
      current.current = null;
      setTip(null);
    };
    const over = (e: Event) => show(e.target);
    const out = (e: PointerEvent) => {
      const to = e.relatedTarget instanceof Element ? e.relatedTarget.closest('[data-tip]') : null;
      if (to !== current.current) show(e.relatedTarget);
    };
    const key = (e: KeyboardEvent) => e.key === 'Escape' && hide();
    el.addEventListener('pointerover', over);
    el.addEventListener('pointerout', out);
    el.addEventListener('focusin', over);
    el.addEventListener('focusout', hide);
    el.addEventListener('pointerdown', hide);
    window.addEventListener('keydown', key);
    window.addEventListener('scroll', hide, true);
    return () => {
      el.removeEventListener('pointerover', over);
      el.removeEventListener('pointerout', out);
      el.removeEventListener('focusin', over);
      el.removeEventListener('focusout', hide);
      el.removeEventListener('pointerdown', hide);
      window.removeEventListener('keydown', key);
      window.removeEventListener('scroll', hide, true);
    };
  }, [root]);

  if (!tip) return null;
  return (
    <div
      className={`cp-tip cp-float-tip ${tip.below ? 'below' : ''}`}
      role="tooltip"
      style={{ left: tip.x, top: tip.y }}
    >
      {tip.text}
    </div>
  );
}
