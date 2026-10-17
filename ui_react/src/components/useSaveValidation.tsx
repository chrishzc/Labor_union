import { useEffect, useRef, useState, type RefObject } from 'react';

type SaveField = {
  value: string | number | null | undefined;
  label: string;
  ref: RefObject<HTMLElement | null>;
  valid?: boolean;
  message?: string;
};

/** Presentation-only checks before the existing save workflow starts. */
export function useSaveValidation() {
  const [warning, setWarning] = useState<string | null>(null);
  const clearField = useRef<(() => void) | null>(null);
  const invalidField = useRef<HTMLElement | null>(null);
  const invalidValue = useRef<string | null>(null);
  useEffect(() => () => clearField.current?.(), []);
  useEffect(() => {
    const element = invalidField.current;
    const currentValue = element && 'value' in element ? String(element.value) : null;
    if (warning && element && (!element.isConnected || currentValue !== invalidValue.current)) {
      clearField.current?.();
      setWarning(null);
    }
  });

  const validate = (fields: SaveField[]) => {
    clearField.current?.();
    setWarning(null);
    const missing = fields.find(field => !(field.valid ?? String(field.value ?? '').trim().length > 0));
    if (!missing) return true;
    const message = missing.message ?? `請填寫或選擇「${missing.label}」後再儲存。`;
    const element = missing.ref.current;
    invalidField.current = element;
    invalidValue.current = element && 'value' in element ? String(element.value) : null;
    if (element) {
      const previous = element.getAttribute('aria-invalid');
      element.setAttribute('aria-invalid', 'true');
      const clear = () => {
        if (previous === null) element.removeAttribute('aria-invalid');
        else element.setAttribute('aria-invalid', previous);
        element.removeEventListener('input', corrected);
        element.removeEventListener('change', corrected);
        clearField.current = null;
        invalidField.current = null;
      };
      const corrected = () => { clear(); setWarning(null); };
      element.addEventListener('input', corrected);
      element.addEventListener('change', corrected);
      clearField.current = clear;
    }
    setWarning(message);
    window.alert(message);
    if (element) {
      for (let parent = element.parentElement; parent; parent = parent.parentElement) {
        if (parent instanceof HTMLDetailsElement) parent.open = true;
      }
      element.scrollIntoView?.({ block: 'center', behavior: 'auto' });
      element.focus();
    }
    return false;
  };

  const feedback = warning ? <span role="alert" style={{ display: 'block', color: 'var(--md-sys-color-error)', marginBlock: 8 }}>{warning}</span> : null;
  return { validate, feedback };
}
