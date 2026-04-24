import { createContext, useCallback, useContext, useState } from 'react';

const ModalContext = createContext(null);

export function ModalProvider({ children }) {
  const [modal, setModal] = useState(null);

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

  return (
    <ModalContext.Provider value={{ confirm, alert }}>
      {children}
      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="bg-fantasy-panel border border-slate-600 rounded-lg shadow-2xl p-6 max-w-md w-full mx-4">
            <h2 className={`text-lg font-serif font-bold mb-3 ${modal.danger ? 'text-red-400' : 'text-fantasy-accent'}`}>
              {modal.title}
            </h2>
            <p className="text-slate-300 text-sm mb-6 whitespace-pre-wrap">{modal.message}</p>
            <div className="flex justify-end gap-2">
              {modal.type === 'confirm' && (
                <button
                  onClick={modal.onCancel}
                  className="px-4 py-2 rounded bg-slate-700 hover:bg-slate-600 text-slate-200 text-sm transition"
                >{modal.cancelLabel}</button>
              )}
              <button
                onClick={modal.onConfirm}
                className={`px-4 py-2 rounded text-white text-sm font-semibold transition ${
                  modal.danger
                    ? 'bg-red-700 hover:bg-red-600'
                    : 'bg-fantasy-accent hover:bg-amber-600'
                }`}
              >{modal.confirmLabel}</button>
            </div>
          </div>
        </div>
      )}
    </ModalContext.Provider>
  );
}

export function useModal() {
  const ctx = useContext(ModalContext);
  if (!ctx) throw new Error('useModal must be used inside ModalProvider');
  return ctx;
}
