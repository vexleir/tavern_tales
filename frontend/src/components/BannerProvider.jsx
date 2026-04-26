import { useCallback, useMemo, useState } from 'react';
import BannerContext from '../contexts/BannerContext';

export default function BannerProvider({ children }) {
  const [banners, setBanners] = useState([]);

  const remove = useCallback((id) => {
    setBanners(b => b.filter(x => x.id !== id));
  }, []);

  const push = useCallback((type, message, { timeout = 6000 } = {}) => {
    const id = Math.random().toString(36).slice(2);
    setBanners(b => [...b, { id, type, message }]);
    if (timeout > 0) setTimeout(() => remove(id), timeout);
    return id;
  }, [remove]);

  const api = useMemo(() => ({
    error: (m, opts) => push('error', m, opts),
    warn: (m, opts) => push('warn', m, opts),
    info: (m, opts) => push('info', m, opts),
    dismiss: remove
  }), [push, remove]);

  return (
    <BannerContext.Provider value={api}>
      {children}
      <div className="fixed top-4 right-4 z-40 flex flex-col gap-2 max-w-sm">
        {banners.map(b => (
          <div
            key={b.id}
            className={`rounded shadow-lg p-3 text-sm border flex items-start gap-2 ${
              b.type === 'error' ? 'bg-red-900/90 border-red-700 text-red-100' :
              b.type === 'warn'  ? 'bg-amber-900/90 border-amber-700 text-amber-100' :
                                   'bg-slate-800/90 border-slate-600 text-slate-200'
            }`}
          >
            <span className="flex-1">{b.message}</span>
            <button onClick={() => remove(b.id)} className="text-white/70 hover:text-white">x</button>
          </div>
        ))}
      </div>
    </BannerContext.Provider>
  );
}
