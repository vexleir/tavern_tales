import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ModalContext from '../contexts/ModalContext';

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function ModalProvider({ children }) {
  const [modal, setModal] = useState(null);
  const dialogRef = useRef(null);
  const returnFocusRef = useRef(null);

  const close = useCallback(() => setModal(null), []);

  const confirm = useCallback(({ title, message, confirmLabel = 'Confirm', cancelLabel = 'Cancel', danger = false }) => {
    return new Promise((resolve) => {
      setModal({
        type: 'confirm',
        title, message, confirmLabel, cancelLabel, danger,
        onConfirm: () => { close(); resolve(true); },
        onCancel: () => { close(); resolve(false); }
      });
    });
  }, [close]);

  const alert = useCallback(({ title, message, confirmLabel = 'OK' }) => {
    return new Promise((resolve) => {
      setModal({
        type: 'alert',
        title, message, confirmLabel,
        onConfirm: () => { close(); resolve(); }
      });
    });
  }, [close]);

  // Focus trap: save caller focus, move into modal, restore on close.
  useEffect(() => {
    if (!modal) return undefined;
    returnFocusRef.current = document.activeElement;
    const el = dialogRef.current;
    if (el) {
      const first = el.querySelectorAll(FOCUSABLE)[0];
      if (first) first.focus();
    }
    return () => {
      try { returnFocusRef.current?.focus(); } catch { /* ignore */ }
    };
  }, [modal]);

  // Keyboard handler: Tab cycles within modal, Escape cancels.
  const handleKeyDown = useCallback((e) => {
    if (!dialogRef.current) return;
    if (e.key === 'Escape') {
      if (modal?.onCancel) modal.onCancel();
      else if (modal?.onConfirm) modal.onConfirm();
      return;
    }
    if (e.key !== 'Tab') return;
    const focusable = Array.from(dialogRef.current.querySelectorAll(FOCUSABLE));
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey) {
      if (document.activeElement === first) { e.preventDefault(); last.focus(); }
    } else {
      if (document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  }, [modal]);

  const api = useMemo(() => ({ confirm, alert }), [confirm, alert]);

  return (
    <ModalContext.Provider value={api}>
      {children}
      {modal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
          onKeyDown={handleKeyDown}
          role="dialog"
          aria-modal="true"
          aria-labelledby="modal-title"
        >
          <div ref={dialogRef} className="bg-fantasy-panel border border-slate-600 rounded-lg shadow-2xl p-6 max-w-md w-full mx-4">
            <h2 id="modal-title" className={`text-lg font-serif font-bold mb-3 ${modal.danger ? 'text-red-400' : 'text-fantasy-accent'}`}>
              {modal.title}
            </h2>
            <p className="text-slate-300 text-sm mb-6 whitespace-pre-wrap">{modal.message}</p>
            <div className="flex justify-end gap-2">
              {modal.type === 'confirm' && (
                <button
                  onClick={modal.onCancel}
                  className="px-4 py-2 rounded bg-slate-700 hover:bg-slate-600 text-slate-200 text-sm transition focus:outline-none focus:ring-2 focus:ring-slate-400"
                >{modal.cancelLabel}</button>
              )}
              <button
                onClick={modal.onConfirm}
                className={`px-4 py-2 rounded text-white text-sm font-semibold transition focus:outline-none focus:ring-2 focus:ring-offset-1 ${
                  modal.danger
                    ? 'bg-red-700 hover:bg-red-600 focus:ring-red-400'
                    : 'bg-fantasy-accent hover:bg-amber-600 focus:ring-amber-400'
                }`}
              >{modal.confirmLabel}</button>
            </div>
          </div>
        </div>
      )}
    </ModalContext.Provider>
  );
}
