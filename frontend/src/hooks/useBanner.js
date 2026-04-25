import { useContext } from 'react';
import BannerContext from '../contexts/BannerContext';

export default function useBanner() {
  const ctx = useContext(BannerContext);
  if (!ctx) throw new Error('useBanner must be used inside BannerProvider');
  return ctx;
}
